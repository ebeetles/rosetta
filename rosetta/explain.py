"""Optional: have Claude say which equivalent fits best and how the rest differ."""

import os

from dotenv import load_dotenv

from .db import ROOT

MODEL = "claude-opus-5-5"

SYSTEM = """You compare idioms across Chinese and English for a language learner.
You get one source idiom with its dictionary meaning, and up to five candidate
equivalents from the other language that a vector search ranked by meaning.

Write a short, concrete note:
1. Name the single closest match and say why in one sentence.
2. For each other candidate, one line on how it differs: tone, register,
   situation, or a different shade of meaning.
3. Flag any false friend: a candidate that sounds close but implies something
   different (for example "it's not too late" versus "it's already too late").
   If none of the candidates truly fits, say so and suggest a better idiom.

Plain text, no headings, under 180 words. Write in English, quoting idioms in
their original script."""


class ExplainUnavailable(Exception):
    """Raised with a one-line, user-facing reason when explain can't run."""


def _client():
    load_dotenv(ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ExplainUnavailable(
            "explain needs ANTHROPIC_API_KEY; copy .env.example to .env and add your key."
        )
    import anthropic

    return anthropic.Anthropic()


def _prompt(record: dict, matches: list[dict]) -> str:
    lines = [f"Source idiom ({record['lang']}): {record['idiom']}"]
    if record.get("pinyin"):
        lines.append(f"Pinyin: {record['pinyin']}")
    lines.append(f"Meaning: {record['meaning']}")
    lines.append("\nCandidates, closest first (cosine distance in parentheses):")
    for i, m in enumerate(matches, 1):
        lines.append(f"{i}. {m['idiom']} ({m['distance']:.2f}): {m['meaning']}")
    return "\n".join(lines)


def explain(record: dict, matches: list[dict]) -> str:
    import anthropic

    client = _client()
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            output_config={"effort": "medium"},
            # On a safety decline, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": _prompt(record, matches)}],
        )
    except anthropic.AuthenticationError:
        raise ExplainUnavailable("The Anthropic API rejected the key in .env.")
    except anthropic.RateLimitError:
        raise ExplainUnavailable("Rate limited by the Anthropic API; try again in a minute.")
    except anthropic.APIStatusError as e:
        raise ExplainUnavailable(f"Anthropic API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise ExplainUnavailable("Couldn't reach the Anthropic API; check your connection.")

    if response.stop_reason == "refusal":
        raise ExplainUnavailable("Claude declined to explain this one.")
    return "".join(b.text for b in response.content if b.type == "text").strip()
