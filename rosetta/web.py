"""A small web front end on top of the same db.py. Start it with `python -m rosetta serve`."""

import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, enrich
from .explain import has_key

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
    return {**db.stats(), "has_key": has_key(), "build": _build_state()}


@app.get("/api/idiom")
def idiom(idiom: str):
    return _record(idiom)


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
    translating = False
    if item.lang == "zh":
        # Pinyin is instant; English takes a Claude call, so it runs in the background.
        enrich.enrich(ids=[saved["id"]], translate_too=False)
        saved = db.get(saved["idiom"]) or saved
        if has_key():
            threading.Thread(target=enrich.enrich, kwargs={"ids": [saved["id"]]}, daemon=True).start()
            translating = True
    return {"saved": saved, "duplicate": None, "nearest": nearest, "translating": translating}


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


# ---------------------------------------------------------------- build


_build_lock = threading.Lock()
_build = {"state": "idle", "phase": "", "done": 0, "total": 0, "message": "", "started": 0.0}


def _build_state() -> dict:
    with _build_lock:
        state = dict(_build)
    state["elapsed"] = round(time.time() - state["started"], 1) if state["started"] else 0
    return state


def _set(**fields) -> None:
    with _build_lock:
        _build.update(fields)


def _run_build(translate_too: bool) -> None:
    from . import data

    try:
        _set(phase="download", done=0, total=0, message="Downloading and cleaning both datasets")
        records = data.load_clean()

        stored = len(db.meaning().get(include=[])["ids"])
        _set(phase="embedding", done=min(stored, len(records)), total=len(records),
             message=f"Embedding with {db.models_label()}")

        def embedded(n: int) -> None:
            with _build_lock:
                _build["done"] += n

        added = db.build(records, progress=embedded)

        def enriched(phase: str, done: int, total: int) -> None:
            label = "Adding pinyin" if phase == "pinyin" else "Translating into English with Claude"
            _set(phase=phase, done=done, total=total, message=label)

        summary = enrich.enrich(translate_too=translate_too, progress=enriched)
        message = (
            f"Added {added:,} idioms, pinyin for {summary['pinyin']:,}, "
            f"English for {summary['english']:,}."
        )
        if summary["skipped"]:
            message += f" {summary['skipped']}"
        _set(state="done", phase="", message=message)
    except Exception as e:  # surfaced in the UI instead of a silent dead thread
        _set(state="error", phase="", message=f"Build failed: {e}")


class BuildRequest(BaseModel):
    translate: bool = True


@app.post("/api/build")
def start_build(req: BuildRequest):
    with _build_lock:
        if _build["state"] == "running":
            raise HTTPException(409, detail="A build is already running.")
        _build.update(state="running", phase="", done=0, total=0, message="Starting", started=time.time())
    threading.Thread(target=_run_build, args=(req.translate,), daemon=True).start()
    return _build_state()


@app.get("/api/build")
def build_status():
    return _build_state()
