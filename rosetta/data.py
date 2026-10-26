"""Download and clean both idiom datasets into data/clean/{zh,en}.jsonl."""

import csv
import json
import random
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"
PAIRS_CSV = ROOT / "eval" / "pairs.csv"

XINHUA_URL = "https://raw.githubusercontent.com/pwxcoo/chinese-xinhua/master/data/idiom.json"
SAMPLE_SIZE = 2000
SEED = 42


# ---------------------------------------------------------------- shared helpers


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def make_id(lang: str, idiom: str) -> str:
    return f"zh-{idiom}" if lang == "zh" else f"en-{slug(idiom)}"


# Well-known idioms people try first, plus the snake idioms that make
# `compare 画蛇添足` show the literal-vs-meaning contrast. Random sampling
# would otherwise keep only a handful of them.
SHOWCASE = {
    "zh": {
        "打草惊蛇", "杯弓蛇影", "虎头蛇尾", "多此一举", "画龙点睛", "守株待兔", "井底之蛙",
        "掩耳盗铃", "塞翁失马", "叶公好龙", "狐假虎威", "刻舟求剑", "拔苗助长", "半途而废",
        "自相矛盾", "一举两得", "对症下药", "入乡随俗", "水滴石穿", "望梅止渴", "卧薪尝胆",
    },
    "en": {
        "carry coals to newcastle", "cross the rubicon", "bite the hand that feeds one",
        "mum's the word", "it's no use crying over spilled milk", "beat a dead horse",
        "let the cat out of the bag", "when in rome, do as the romans do",
        "the last straw", "a blessing in disguise", "kick the bucket", "spill the beans",
    },
}


def forced_idioms() -> dict[str, set[str]]:
    """Idioms that sampling must keep: eval/pairs.csv plus the showcase list."""
    forced = {lang: set(words) for lang, words in SHOWCASE.items()}
    if PAIRS_CSV.exists():
        with PAIRS_CSV.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                forced["zh"].add(row["zh"].strip())
                forced["en"].add(row["en"].strip().lower())
    return forced


def sample(records: list[dict], forced: set[str], key) -> list[dict]:
    """Forced records first, then a seeded random fill up to SAMPLE_SIZE."""
    must = [r for r in records if key(r) in forced]
    rest = [r for r in records if key(r) not in forced]
    random.Random(SEED).shuffle(rest)
    return must + rest[: max(0, SAMPLE_SIZE - len(must))]


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------- Chinese


# Sentences that start the figurative sense. Xinhua explanations usually open
# with the literal picture ("画蛇时给蛇添上脚。比喻…"); keeping that part would
# pull the literal words back into the meaning embedding.
_ZH_SENSE_START = ("比喻", "形容", "指", "喻", "意思是", "意为")
# Secondary senses ("也比喻…") muddy the main one, so the gloss stops there.
_ZH_SECONDARY = ("也比喻", "又比喻", "也指", "又指", "也作", "亦作", "也形容", "又形容")


def clean_zh_meaning(explanation: str) -> str:
    # Xinhua uses ◇ as a sentence break inside some explanations.
    text = explanation.strip().replace("◇", "。")
    sentences = [s for s in re.split(r"(?<=。)", text) if s.strip()]
    start = next(
        (i for i, s in enumerate(sentences) if s.lstrip().startswith(_ZH_SENSE_START)),
        None,
    )
    # A sense marker mid-sentence ("自己过了河，便把桥拆掉。比喻…" is caught above,
    # but "…，比喻…" is not): fall back to slicing at the first 比喻.
    if start is None and "比喻" in text:
        text = text[text.index("比喻") :]
    elif start is not None:
        text = "".join(sentences[start:])
    for marker in _ZH_SECONDARY:
        idx = text.find(marker, 1)
        if idx > 0:
            text = text[:idx]
    return text.strip()


def download_xinhua() -> Path:
    path = RAW_DIR / "idiom.json"
    if not path.exists():
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(XINHUA_URL, path)
    return path


def clean_zh() -> list[dict]:
    raw = json.loads(download_xinhua().read_text(encoding="utf-8"))
    forced = forced_idioms()["zh"]
    seen, with_example, without_example = set(), [], []
    for entry in raw:
        word = entry.get("word", "").strip()
        explanation = (entry.get("explanation") or "").strip()
        if len(word) != 4 or word in seen or len(explanation) < 6:
            continue
        meaning = clean_zh_meaning(explanation)
        if len(meaning) < 4:
            continue
        seen.add(word)
        example = (entry.get("example") or "").strip()
        record = {
            "id": make_id("zh", word),
            "lang": "zh",
            "idiom": word,
            "meaning": meaning,
            "example": example.replace("～", word).split("★")[0].strip(),
            "pinyin": entry.get("pinyin", "").strip(),
            "source": "xinhua",
        }
        (with_example if example else without_example).append(record)
    # Having an example sentence is a rough proxy for common usage.
    pool = with_example if len(with_example) >= SAMPLE_SIZE else with_example + without_example
    # Forced idioms may lack an example; make sure they're still in the pool.
    pool_words = {r["idiom"] for r in pool}
    pool += [r for r in without_example if r["idiom"] in forced and r["idiom"] not in pool_words]
    return sample(pool, forced, key=lambda r: r["idiom"])


# ---------------------------------------------------------------- English


def strip_parens(text: str) -> str:
    """Remove parentheticals, innermost first, so nested ones go too."""
    prev = None
    while prev != text:
        prev, text = text, re.sub(r"\([^()]*\)", " ", text)
    return text.replace("(", " ").replace(")", " ")


def normalize_phrase(phrase: str) -> str:
    """'cast (one’s) pearls before swine' -> "cast pearls before swine"."""
    text = phrase.replace("’", "'").replace("‘", "'").replace("†", "").replace("*", "")
    text = strip_parens(text)
    text = re.sub(r"\s+", " ", text).strip().rstrip(".").strip()
    return text


# Usage labels that sit right after "Fig." and aren't part of the meaning.
_EN_LABELS = re.compile(r"^((Cliché|Prov\.|Inf\.|Sl\.|Rur\.|Euph\.|Fig\.|Lit\.)\s*)+")


def extract_sense(definition: str, marker: str = "Fig.") -> str | None:
    """The text after `marker`, up to the first example (`_`) or next numbered sense."""
    idx = definition.find(marker)
    if idx < 0:
        return None
    text = definition[idx + len(marker) :]
    text = re.split(r"_|\s\d+\.\s", text, maxsplit=1)[0]
    text = strip_parens(text)  # (*Typically: be ~.), (Alludes to …), etc.
    text = _EN_LABELS.sub("", text.strip())
    text = re.sub(r"\s+", " ", text).strip().rstrip(";,").strip()
    if text and not text.endswith((".", "!", "?")):
        text += "."
    return text or None


def load_englishidioms() -> list[dict]:
    from importlib.resources import files

    raw = files("englishidioms").joinpath("phrases.json").read_text(encoding="utf-8")
    return json.loads(raw)["dictionary"]


def clean_en() -> list[dict]:
    forced = forced_idioms()["en"]
    by_meaning: dict[str, dict] = {}
    for entry in load_englishidioms():
        idiom = normalize_phrase(entry["phrase"])
        key = idiom.lower()
        meaning = extract_sense(entry["definition"])
        # Test-pair idioms may be proverbs rather than Fig. entries; take that sense.
        if meaning is None and key in forced:
            meaning = extract_sense(entry["definition"], "Prov.") or extract_sense(
                entry["definition"], ""
            )
        if not meaning or len(meaning) < 8:
            continue
        # One- and two-word entries are mostly phrasal verbs ("roll by").
        if len(idiom.split()) < 3 and key not in forced:
            continue
        # Variants share one definition ("easy as pie", "easy as A, B, C"…).
        # Keep one per meaning so they don't crowd every result list.
        if meaning in by_meaning and by_meaning[meaning]["idiom"].lower() in forced:
            continue
        if meaning in by_meaning and key not in forced:
            continue
        by_meaning[meaning] = {
            "id": make_id("en", idiom),
            "lang": "en",
            "idiom": idiom,
            "meaning": meaning,
            "example": _first_example(entry["definition"]),
            "pinyin": "",
            "source": "mcgraw-hill",
        }
    # Ids must be unique too (two senses of one phrase).
    unique = {r["id"]: r for r in by_meaning.values()}
    return sample(list(unique.values()), forced, key=lambda r: r["idiom"].lower())


def _first_example(definition: str) -> str:
    fig = definition.find("Fig.")
    parts = definition[fig if fig >= 0 else 0 :].split("_")
    if len(parts) < 2:
        return ""
    return re.split(r"\s\d+\.\s", parts[1])[0].strip()


# ---------------------------------------------------------------- entry point


def clean_all() -> tuple[Path, Path]:
    zh_path, en_path = CLEAN_DIR / "zh.jsonl", CLEAN_DIR / "en.jsonl"
    write_jsonl(zh_path, clean_zh())
    write_jsonl(en_path, clean_en())
    return zh_path, en_path


def load_clean() -> list[dict]:
    zh_path, en_path = CLEAN_DIR / "zh.jsonl", CLEAN_DIR / "en.jsonl"
    if not (zh_path.exists() and en_path.exists()):
        clean_all()
    return read_jsonl(zh_path) + read_jsonl(en_path)


if __name__ == "__main__":
    for path in clean_all():
        print(path, sum(1 for _ in path.open(encoding="utf-8")))
