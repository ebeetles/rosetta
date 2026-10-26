"""A small web front end on top of the same db.py. Start it with `python -m rosetta serve`."""

import random
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db

WEB_DIR = db.ROOT / "web"


@asynccontextmanager
async def lifespan(app):
    # Open the store and load the models before the first request, not during it.
    db.stats()
    db.embedding_function()(["warm up"])
    yield


app = FastAPI(title="Idiom Rosetta", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def _record(idiom: str) -> dict:
    record = db.get(idiom)
    if record is None:
        raise HTTPException(404, detail=f"“{idiom}” isn't in the database yet.")
    return record


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/stats")
def stats():
    return db.stats()


@app.get("/api/find")
def find(q: str, lang: str | None = None, k: int = 8):
    return {"query": q, "results": db.find(q, lang=lang or None, k=k)}


@app.get("/api/equiv")
def equiv(idiom: str, k: int = 5):
    record = _record(idiom)
    return {"idiom": record, "results": db.equiv(record, k=k)}


@app.get("/api/compare")
def compare(idiom: str, k: int = 6):
    record = _record(idiom)
    by_words, by_meaning = db.compare(record, k=k)
    return {"idiom": record, "by_words": by_words, "by_meaning": by_meaning}


@app.get("/api/random")
def random_idiom(lang: str | None = None):
    found = db.meaning().get(where={"lang": lang} if lang else None, include=["metadatas"])
    return random.choice(found["metadatas"])


class NewIdiom(BaseModel):
    idiom: str
    lang: str
    meaning: str
    example: str = ""
    pinyin: str = ""
    force: bool = False


@app.post("/api/add")
def add(item: NewIdiom):
    if item.lang not in db.LANGS or not item.idiom.strip() or not item.meaning.strip():
        raise HTTPException(400, detail="An idiom, its language, and its meaning are required.")
    nearest = db.nearest_meanings(item.meaning, k=3)
    exact = db.get(item.idiom)
    duplicate = exact or (nearest[0] if nearest and nearest[0]["distance"] < db.DUPLICATE_THRESHOLD else None)
    if duplicate and not item.force:
        return {"saved": None, "duplicate": {**duplicate, "exact": bool(exact)}, "nearest": nearest}
    saved = db.add(item.idiom, item.lang, item.meaning, item.example, item.pinyin)
    return {"saved": saved, "duplicate": None, "nearest": nearest}


class ExplainRequest(BaseModel):
    idiom: str


@app.post("/api/explain")
def explain(req: ExplainRequest):
    from .explain import ExplainUnavailable, explain as run_explain

    record = _record(req.idiom)
    matches = db.equiv(record, k=5)
    try:
        return {"note": run_explain(record, matches)}
    except ExplainUnavailable as e:
        raise HTTPException(503, detail=str(e))
