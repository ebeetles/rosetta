"""The persistent Chroma store: two collections holding the same ids.

`literal` embeds each idiom's own words; `meaning` embeds its gloss. Every
search is a query against one or both of them.
"""

import re
import threading
import uuid
from pathlib import Path
from typing import Callable

from .embed import embedding_function, models_label

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "chroma_db"
BATCH_SIZE = 256
# Below this cosine distance, a new idiom's meaning is probably already stored.
DUPLICATE_THRESHOLD = 0.1

LANGS = ("zh", "en")
OTHER = {"zh": "en", "en": "zh"}


# The web server answers requests on several threads; Chroma's client and our
# collection handles must each be created exactly once.
_lock = threading.RLock()
_client = None
_collections: dict = {}


def client():
    global _client
    with _lock:
        if _client is None:
            import chromadb

            _client = chromadb.PersistentClient(path=str(DB_PATH))
        return _client


class ModelMismatch(Exception):
    """The store was built with different embedding models than the ones configured."""


def _collection(name: str):
    with _lock:
        if name not in _collections:
            _collections[name] = _open_collection(name)
        return _collections[name]


def _open_collection(name: str):
    collection = client().get_or_create_collection(
        name=name,
        embedding_function=embedding_function(),
        configuration={"hnsw": {"space": "cosine"}},
        metadata={"models": models_label()},
    )
    built_with = (collection.metadata or {}).get("models")
    if built_with and built_with != models_label():
        raise ModelMismatch(
            f"chroma_db/ was built with {built_with}, but the configured models are "
            f"{models_label()}. Set ROSETTA_MODELS to match, or delete chroma_db/ and run build."
        )
    return collection


def literal():
    return _collection("literal")


def meaning():
    return _collection("meaning")


# ---------------------------------------------------------------- records


def lookup_key(idiom: str) -> str:
    """How an idiom is matched when a user types it: case and quotes don't matter."""
    text = idiom.strip().replace("’", "'").lower().rstrip(".!?")
    return re.sub(r"\s+", " ", text)


def _metadata(record: dict) -> dict:
    return {
        "lang": record["lang"],
        "idiom": record["idiom"],
        "key": lookup_key(record["idiom"]),
        "meaning": record["meaning"],
        "example": record.get("example") or "",
        "pinyin": record.get("pinyin") or "",
        "source": record.get("source") or "user",
    }


def detect_lang(text: str) -> str:
    return "zh" if re.search(r"[一-鿿]", text) else "en"


# ---------------------------------------------------------------- writes


def build(records: list[dict], progress: Callable[[int], None] | None = None) -> int:
    """Upsert records into both collections. Already-stored ids are skipped."""
    stored = set(meaning().get(include=[])["ids"]) & set(literal().get(include=[])["ids"])
    todo = [r for r in records if r["id"] not in stored]
    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start : start + BATCH_SIZE]
        ids = [r["id"] for r in batch]
        metas = [_metadata(r) for r in batch]
        literal().upsert(ids=ids, documents=[r["idiom"] for r in batch], metadatas=metas)
        meaning().upsert(ids=ids, documents=[r["meaning"] for r in batch], metadatas=metas)
        if progress:
            progress(len(batch))
    return len(todo)


def add(idiom: str, lang: str, gloss: str, example: str = "", pinyin: str = "") -> dict:
    record = {
        "id": f"user-{uuid.uuid4()}",
        "lang": lang,
        "idiom": idiom.strip(),
        "meaning": gloss.strip(),
        "example": example.strip(),
        "pinyin": pinyin.strip(),
        "source": "user",
    }
    meta = _metadata(record)
    literal().add(ids=[record["id"]], documents=[record["idiom"]], metadatas=[meta])
    meaning().add(ids=[record["id"]], documents=[record["meaning"]], metadatas=[meta])
    return {**meta, "id": record["id"]}


# ---------------------------------------------------------------- reads


def get(idiom: str) -> dict | None:
    """The stored record for an idiom, or None if it isn't in the database."""
    found = meaning().get(where={"key": lookup_key(idiom)}, limit=1)
    if not found["ids"]:
        return None
    return {**found["metadatas"][0], "id": found["ids"][0]}


def _vector(collection, record_id: str):
    return collection.get(ids=[record_id], include=["embeddings"])["embeddings"][0]


def _hits(result, skip_id: str | None = None, k: int | None = None) -> list[dict]:
    hits = [
        {**meta, "id": rid, "distance": float(dist)}
        for rid, meta, dist in zip(
            result["ids"][0], result["metadatas"][0], result["distances"][0]
        )
        if rid != skip_id
    ]
    return hits[:k] if k else hits


def find(text: str, lang: str | None = None, k: int = 8) -> list[dict]:
    """Idioms whose meaning fits a plain-language description."""
    where = {"lang": lang} if lang else None
    result = meaning().query(query_texts=[text], n_results=k, where=where)
    return _hits(result)


def equiv(record: dict, k: int = 5) -> list[dict]:
    """Nearest idioms in the other language, searched from the stored meaning vector."""
    result = meaning().query(
        query_embeddings=[_vector(meaning(), record["id"])],
        n_results=k,
        where={"lang": OTHER[record["lang"]]},
    )
    return _hits(result)


def compare(record: dict, k: int = 6) -> tuple[list[dict], list[dict]]:
    """(nearest by the idiom's words, nearest by its meaning), the idiom itself dropped."""
    by_words = literal().query(
        query_embeddings=[_vector(literal(), record["id"])], n_results=k + 1
    )
    by_meaning = meaning().query(
        query_embeddings=[_vector(meaning(), record["id"])], n_results=k + 1
    )
    return (
        _hits(by_words, skip_id=record["id"], k=k),
        _hits(by_meaning, skip_id=record["id"], k=k),
    )


def nearest_meanings(gloss: str, k: int = 3) -> list[dict]:
    """The duplicate check behind `add`."""
    return find(gloss, k=k)


def stats() -> dict:
    out = {"literal": literal().count(), "meaning": meaning().count()}
    for lang in LANGS:
        out[lang] = len(meaning().get(where={"lang": lang}, include=[])["ids"])
    out["user"] = len(meaning().get(where={"source": "user"}, include=[])["ids"])
    return out

