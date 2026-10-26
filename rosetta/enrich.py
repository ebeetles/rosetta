"""Pinyin and English for the Chinese side, stored as extra metadata.

Embeddings are untouched: the meaning collection still embeds the Chinese
gloss, so search results don't change. This only adds what a reader needs:

    pinyin          画蛇添足 -> huà shé tiān zú (filled in when missing)
    meaning_pinyin  pinyin for the Chinese explanation
    idiom_en        the idiom's literal picture: "draw a snake and add feet"
    meaning_en      the explanation in English

Pinyin comes from pypinyin, offline. English comes from Claude, translated once
in batches and cached in data/translations.json, so a rebuild never pays twice.
"""

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from pydantic import BaseModel

from . import db
from .explain import ExplainUnavailable, claude_client, has_key

MODEL = "claude-opus-5-5"
CHUNK = 40
WORKERS = 4
CACHE_PATH = db.ROOT / "data" / "translations.json"

_cache_lock = threading.Lock()


# ---------------------------------------------------------------- pinyin

_PUNCT = {"，": ",", "。": ".", "；": ";", "：": ":", "、": ",", "！": "!", "？": "?",
          "“": '"', "”": '"', "‘": "'", "’": "'", "（": "(", "）": ")", "《": "«", "》": "»"}


def to_pinyin(text: str) -> str:
    """'形容说话谨慎，严守秘密。' -> 'xíng róng shuō huà jǐn shèn, yán shǒu mì mì.'"""
    from pypinyin import Style, pinyin

    words = [syllables[0] for syllables in pinyin(text, style=Style.TONE, errors="default")]
    out = " ".join(_PUNCT.get(w, w) for w in words)
    out = re.sub(r"\s+([,.;:!?)»])", r"\1", out)  # no space before closing punctuation
    out = re.sub(r"([(«])\s+", r"\1", out)
    return re.sub(r"\s+", " ", out).strip()


# ---------------------------------------------------------------- translation


class _Item(BaseModel):
    n: int
    literal: str
    meaning: str


class _Batch(BaseModel):
    items: list[_Item]


SYSTEM = """You translate Chinese idioms (chengyu) and their dictionary explanations
into English for language learners. For each numbered item return:

- literal: the idiom's literal picture in plain English, lowercase, no final
  period. Translate the words, not the moral: 画蛇添足 -> "draw a snake and add
  feet", 九牛一毛 -> "one hair from nine oxen". Name people and places in
  allusions the way a reader would recognize them (班门弄斧 -> "wield an axe at
  Lu Ban's door").
- meaning: a faithful English translation of the explanation, written like a
  dictionary gloss. Leave out framing words such as 比喻 ("figuratively") or
  形容 ("describes") and give the sense directly: 比喻做了多余的事，非但无益，
  反而不合适 -> "to do something superfluous that, far from helping, makes
  things worse". Never render 比喻 as "metaphor".

Return every item exactly once, keeping its number."""


def _cache_key(idiom: str, meaning: str) -> str:
    return f"{idiom}\t{meaning}"


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(CACHE_PATH)


def _translate_chunk(client, chunk: list[dict]) -> dict[str, dict]:
    import anthropic

    lines = [f"{i}. {r['idiom']} — {r['meaning']}" for i, r in enumerate(chunk, 1)]
    try:
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            output_config={"effort": "medium"},
            # On a safety decline, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_format=_Batch,
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
    except anthropic.AuthenticationError:
        raise ExplainUnavailable("The Anthropic API rejected the key in .env.")
    except anthropic.APIStatusError as e:
        raise ExplainUnavailable(f"Anthropic API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise ExplainUnavailable("Couldn't reach the Anthropic API; check your connection.")
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return {}
    out = {}
    for item in response.parsed_output.items:
        if 1 <= item.n <= len(chunk) and item.literal.strip() and item.meaning.strip():
            r = chunk[item.n - 1]
            out[_cache_key(r["idiom"], r["meaning"])] = {
                "idiom_en": item.literal.strip(),
                "meaning_en": item.meaning.strip(),
            }
    return out


def translate(records: list[dict], progress: Callable[[int], None] | None = None) -> dict[str, dict]:
    """English for each record, keyed by _cache_key. Cached results cost nothing."""
    with _cache_lock:
        cache = _load_cache()
    todo = [r for r in records if _cache_key(r["idiom"], r["meaning"]) not in cache]
    if progress:
        progress(len(records) - len(todo))
    if todo:
        client = claude_client("Translation")
        chunks = [todo[i : i + CHUNK] for i in range(0, len(todo), CHUNK)]
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(_translate_chunk, client, c): c for c in chunks}
            for future in as_completed(futures):
                result = future.result()
                with _cache_lock:
                    cache.update(result)
                    _save_cache(cache)
                if progress:
                    progress(len(futures[future]))
    return cached(records)


def cached(records: list[dict]) -> dict[str, dict]:
    with _cache_lock:
        cache = _load_cache()
    keys = (_cache_key(r["idiom"], r["meaning"]) for r in records)
    return {k: cache[k] for k in keys if k in cache}


# ---------------------------------------------------------------- enrich


def missing(translate_too: bool = True) -> list[dict]:
    """Chinese records that still lack pinyin or (optionally) English."""
    found = db.meaning().get(where={"lang": "zh"}, include=["metadatas"])
    out = []
    for rid, meta in zip(found["ids"], found["metadatas"]):
        needs_pinyin = not meta.get("meaning_pinyin") or not meta.get("pinyin")
        needs_english = translate_too and not meta.get("idiom_en")
        if needs_pinyin or needs_english:
            out.append({**meta, "id": rid})
    return out


def enrich(
    ids: list[str] | None = None,
    translate_too: bool = True,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Fill in pinyin, then English, for Chinese records that lack them.

    Returns a summary: {"pinyin": n, "english": n, "skipped": reason or ""}.
    progress(phase, done, total) is called as work completes.
    """
    records = missing(translate_too)
    if ids is not None:
        wanted = set(ids)
        records = [r for r in records if r["id"] in wanted]
    summary = {"pinyin": 0, "english": 0, "skipped": ""}

    updates: dict[str, dict] = {}
    for r in records:
        patch = {}
        if not r.get("pinyin"):
            patch["pinyin"] = to_pinyin(r["idiom"])
        if not r.get("meaning_pinyin"):
            patch["meaning_pinyin"] = to_pinyin(r["meaning"])
        if patch:
            updates[r["id"]] = patch
    if updates:
        db.update_metadata(updates)
        summary["pinyin"] = len(updates)
    if progress:
        progress("pinyin", len(records), len(records))

    need_english = [r for r in records if not r.get("idiom_en")] if translate_too else []
    if not need_english:
        return summary
    if not has_key():
        summary["skipped"] = "English translations need ANTHROPIC_API_KEY in .env."
        return summary

    done = 0

    def tick(n: int) -> None:
        nonlocal done
        done += n
        if progress:
            progress("english", min(done, len(need_english)), len(need_english))

    try:
        english = translate(need_english, progress=tick)
    except ExplainUnavailable as e:
        # Batches that finished before the failure are cached; keep them.
        summary["skipped"] = str(e)
        english = cached(need_english)
    patches = {
        r["id"]: english[_cache_key(r["idiom"], r["meaning"])]
        for r in need_english
        if _cache_key(r["idiom"], r["meaning"]) in english
    }
    if patches:
        db.update_metadata(patches)
    summary["english"] = len(patches)
    return summary
