"""The embedding models. Their names live here and nowhere else.

The default is an ensemble of two multilingual models. Each text is embedded by
both, each vector is unit-normalized, and the two are concatenated and scaled by
1/sqrt(2). The cosine similarity of two such vectors is then exactly the average
of the two models' cosine similarities, so Chroma runs the ensemble with no
extra code. Phase 3 test pairs in the top 5 (first sample / final sample, see README):

    paraphrase-multilingual-MiniLM-L12-v2   3 / 3
    sentence-transformers/LaBSE              3 / 3
    intfloat/multilingual-e5-large           5 / 5
    BAAI/bge-m3                              5 / 6
    bge-m3 + e5-large (this ensemble)        7 / 6

ROSETTA_MODELS swaps in a different set, comma-separated, e.g.
ROSETTA_MODELS=paraphrase-multilingual-MiniLM-L12-v2 for a ~470 MB download
instead of ~4.5 GB. A store remembers which models built it (see db.py).
"""

import os
import threading
from functools import lru_cache

import numpy as np
from chromadb import Documents, EmbeddingFunction, Embeddings

DEFAULT_MODELS = "BAAI/bge-m3,intfloat/multilingual-e5-large"
MODEL_NAMES = [m.strip() for m in os.environ.get("ROSETTA_MODELS", DEFAULT_MODELS).split(",") if m.strip()]

# e5 models were trained with a prefix on every input; "query: " is the one for
# symmetric similarity tasks like this.
PREFIXES = {"intfloat/multilingual-e5-large": "query: ", "intfloat/multilingual-e5-base": "query: "}


class EnsembleEmbedding(EmbeddingFunction[Documents]):
    def __init__(self, model_names: list[str]):
        self.model_names = model_names
        self._models = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._models is None:
                from sentence_transformers import SentenceTransformer

                self._models = [SentenceTransformer(name) for name in self.model_names]
            return self._models

    def __call__(self, input: Documents) -> Embeddings:
        parts = []
        for name, model in zip(self.model_names, self._load()):
            prefix = PREFIXES.get(name, "")
            parts.append(
                model.encode([prefix + t for t in input], normalize_embeddings=True, batch_size=32)
            )
        joined = np.concatenate(parts, axis=1) / np.sqrt(len(parts))
        return [row.astype(np.float32) for row in joined]

    # Chroma persists embedding-function configs alongside a collection.
    @staticmethod
    def name() -> str:
        return "rosetta-ensemble"

    def get_config(self) -> dict:
        return {"model_names": self.model_names}

    @staticmethod
    def build_from_config(config: dict) -> "EnsembleEmbedding":
        return EnsembleEmbedding(config["model_names"])


@lru_cache(maxsize=1)
def embedding_function() -> EnsembleEmbedding:
    return EnsembleEmbedding(MODEL_NAMES)


def models_label() -> str:
    return " + ".join(MODEL_NAMES)
