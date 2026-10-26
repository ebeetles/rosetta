"""Phase 3 quality gate: does each Chinese idiom's English equivalent land in its top 5?

    python -m eval.check            # meaning search (what `equiv` does)
    python -m eval.check --literal  # same pairs, searched by the idioms' own words
"""

import argparse
import csv
from pathlib import Path

from rosetta import db

PAIRS = Path(__file__).with_name("pairs.csv")
TOP_K = 5


def rank_of(target: str, hits: list[dict]) -> int | None:
    key = db.lookup_key(target)
    return next((i for i, h in enumerate(hits, 1) if h["key"] == key), None)


def literal_equiv(record: dict, k: int) -> list[dict]:
    vec = db.literal().get(ids=[record["id"]], include=["embeddings"])["embeddings"][0]
    result = db.literal().query(
        query_embeddings=[vec], n_results=k, where={"lang": db.OTHER[record["lang"]]}
    )
    return db._hits(result)


def run(literal: bool = False, k: int = TOP_K) -> list[dict]:
    rows = []
    with PAIRS.open(encoding="utf-8") as f:
        for pair in csv.DictReader(f):
            record = db.get(pair["zh"])
            if record is None or db.get(pair["en"]) is None:
                rows.append({**pair, "rank": None, "top": [], "missing": True})
                continue
            hits = literal_equiv(record, 50) if literal else db.equiv(record, k=50)
            rows.append({
                **pair,
                "rank": rank_of(pair["en"], hits),
                "top": [h["idiom"] for h in hits[:3]],
                "missing": False,
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--literal", action="store_true")
    args = parser.parse_args()

    rows = run(literal=args.literal)
    hits = 0
    for row in rows:
        if row["missing"]:
            status = "MISSING"
        elif row["rank"] and row["rank"] <= TOP_K:
            status = "hit"
        else:
            status = "miss"
        if row["kind"] == "pair" and status == "hit":
            hits += 1
        tag = " (false friend)" if row["kind"] == "false_friend" else ""
        rank = row["rank"] if row["rank"] else ">50"
        print(f"{status:7} {row['zh']} -> {row['en']}{tag}  rank {rank}  top: {', '.join(row['top'])}")
    total = sum(r["kind"] == "pair" for r in rows)
    mode = "literal" if args.literal else "meaning"
    print(f"\n{hits}/{total} test pairs in the top {TOP_K} ({mode} search)")


if __name__ == "__main__":
    main()
