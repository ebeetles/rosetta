"""Command parsing, rich output, and the interactive shell."""

import argparse
import shlex
import time

from rich.console import Console
from rich.padding import Padding
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from . import db
from .embed import models_label

console = Console(highlight=False)

# zh in seal-paste red, en in ink blue: the same pairing the web UI uses.
LANG_STYLE = {"zh": "bold #c8442f", "en": "bold #2f5d8a"}
DIM = "#8a8170"

COMMANDS = [
    ("build", "Download, clean, and embed both datasets (one time; skips what's stored)"),
    ("find <description>", "Idioms that fit a plain-language description  [--lang zh|en] [-k N]"),
    ("equiv <idiom>", "Top 5 equivalents in the other language"),
    ("compare <idiom>", "Nearest by the idiom's words vs. nearest by its meaning"),
    ("add", "Add your own idiom (checks for near-duplicates first)"),
    ("explain <idiom>", "Ask Claude which equivalent fits best and how the others differ"),
    ("stats", "Counts per collection and language"),
    ("serve", "Open the web front end on http://127.0.0.1:8000"),
    ("help / quit", ""),
]


# ---------------------------------------------------------------- rendering


def idiom_text(hit: dict, with_pinyin: bool = False) -> Text:
    text = Text(hit["idiom"], style=LANG_STYLE.get(hit["lang"], "bold"))
    if with_pinyin and hit.get("pinyin"):
        text.append(f"  {hit['pinyin']}", style=f"italic {DIM}")
    return text


def dist(value: float) -> Text:
    # Closer matches read darker; anything past 0.6 is effectively unrelated.
    style = "bold" if value < 0.35 else ("" if value < 0.55 else DIM)
    return Text(f"{value:.2f}", style=style)


def headline(record: dict) -> None:
    line = idiom_text(record, with_pinyin=True)
    line.append("  —  ", style=DIM)
    line.append(record["meaning"])
    console.print(Padding(line, (1, 0, 0, 0)))


def results_table(hits: list[dict], show_lang: bool = False) -> Table:
    table = Table(box=None, show_header=False, padding=(0, 2, 0, 0), pad_edge=False)
    table.add_column(justify="right", style=DIM)
    table.add_column(no_wrap=True)
    if show_lang:
        table.add_column(style=DIM)
    table.add_column(justify="right")
    table.add_column(ratio=1, overflow="fold")
    for i, hit in enumerate(hits, 1):
        cells = [f"{i}.", idiom_text(hit)]
        if show_lang:
            cells.append(hit["lang"])
        cells += [dist(hit["distance"]), Text(hit["meaning"], style="")]
        table.add_row(*cells)
    return table


def require(idiom: str) -> dict | None:
    record = db.get(idiom)
    if record is None:
        console.print(f"[{DIM}]“{idiom}” isn't in the database yet.[/]")
        if Confirm.ask("  Add it now?", default=False):
            return cmd_add(prefill=idiom)
    return record


# ---------------------------------------------------------------- commands


def cmd_build(args) -> None:
    from . import data

    console.print("Cleaning datasets…", style=DIM)
    records = data.load_clean()
    console.print(f"Embedding with [bold]{models_label()}[/] (first run downloads the models)…", style=DIM)
    start = time.perf_counter()
    with Progress(
        TextColumn("  embedding"),
        BarColumn(complete_style="#c8442f"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("embed", total=len(records))
        stored = len(db.meaning().get(include=[])["ids"])
        progress.update(task, completed=min(stored, len(records)))
        added = db.build(records, progress=lambda n: progress.advance(task, n))
    elapsed = time.perf_counter() - start
    console.print(f"Added {added:,} idioms in {elapsed:.1f}s.")
    cmd_stats(args)


def cmd_find(args) -> None:
    text = " ".join(args.text)
    hits = db.find(text, lang=args.lang, k=args.k)
    console.print(Padding(Text(f"Idioms for “{text}”", style="bold"), (1, 0, 0, 0)))
    console.print(Padding(results_table(hits, show_lang=True), (0, 0, 1, 2)))


def cmd_equiv(args) -> None:
    record = require(" ".join(args.idiom))
    if record is None:
        return
    headline(record)
    hits = db.equiv(record, k=args.k)
    console.print(Padding(results_table(hits), (0, 0, 1, 2)))


def cmd_compare(args) -> None:
    record = require(" ".join(args.idiom))
    if record is None:
        return
    by_words, by_meaning = db.compare(record, k=args.k)
    headline(record)
    table = Table(box=None, padding=(0, 4, 0, 0), pad_edge=False, header_style=f"bold {DIM}")
    table.add_column("by its words")
    table.add_column("", justify="right")
    table.add_column("by its meaning")
    table.add_column("", justify="right")
    for left, right in zip(by_words, by_meaning):
        table.add_row(idiom_text(left), dist(left["distance"]), idiom_text(right), dist(right["distance"]))
    console.print(Padding(table, (1, 0, 1, 2)))


def cmd_add(args=None, prefill: str = "") -> dict | None:
    console.print()
    idiom = Prompt.ask("  Idiom", default=prefill or None)
    if not idiom:
        return None
    lang = Prompt.ask("  Language", choices=["zh", "en"], default=db.detect_lang(idiom))
    gloss = Prompt.ask("  Meaning")
    if not gloss:
        console.print(f"  [{DIM}]A meaning is required; nothing saved.[/]")
        return None
    example = Prompt.ask("  Example (optional)", default="")
    pinyin = Prompt.ask("  Pinyin (optional)", default="") if lang == "zh" else ""

    nearest = db.nearest_meanings(gloss, k=3)
    if nearest:
        line = Text("  Closest existing: ", style=DIM)
        for i, hit in enumerate(nearest):
            if i:
                line.append(", ", style=DIM)
            line.append_text(idiom_text(hit))
            line.append(f" ({hit['distance']:.2f})", style=DIM)
        console.print(line)
        top = nearest[0]
        exact = db.get(idiom)
        if top["distance"] < db.DUPLICATE_THRESHOLD or exact:
            if exact:
                console.print(f"  [bold]{exact['idiom']}[/] is already stored.")
            else:
                console.print(f"  [bold]{top['idiom']}[/] has almost the same meaning ({top['distance']:.2f}).")
            if not Confirm.ask("  Save anyway?", default=False):
                return None
    saved = db.add(idiom, lang, gloss, example, pinyin)
    console.print(f"  Saved {saved['idiom']}. It's searchable now.")
    return saved


def cmd_explain(args) -> None:
    from .explain import ExplainUnavailable, explain

    record = require(" ".join(args.idiom))
    if record is None:
        return
    hits = db.equiv(record, k=5)
    headline(record)
    console.print(Padding(results_table(hits), (0, 0, 1, 2)))
    try:
        with console.status("Asking Claude…", spinner="dots"):
            note = explain(record, hits)
    except ExplainUnavailable as e:
        console.print(f"  [{DIM}]{e}[/]")
        return
    console.print(Padding(note, (0, 4, 1, 2)))


def cmd_stats(args=None) -> None:
    s = db.stats()
    table = Table(box=None, show_header=False, padding=(0, 3, 0, 0), pad_edge=False)
    table.add_column(style=DIM)
    table.add_column(justify="right", style="bold")
    table.add_row("literal collection", f"{s['literal']:,}")
    table.add_row("meaning collection", f"{s['meaning']:,}")
    table.add_row(Text("Chinese (zh)", style=LANG_STYLE["zh"]), f"{s['zh']:,}")
    table.add_row(Text("English (en)", style=LANG_STYLE["en"]), f"{s['en']:,}")
    table.add_row("added by you", f"{s['user']:,}")
    table.add_row("stored in", str(db.DB_PATH.relative_to(db.ROOT)) + "/")
    console.print(Padding(table, (1, 0, 1, 2)))


def cmd_serve(args) -> None:
    import uvicorn

    console.print(f"Serving on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    uvicorn.run("rosetta.web:app", host=args.host, port=args.port, log_level="warning")


def cmd_help(args=None) -> None:
    table = Table(box=None, show_header=False, padding=(0, 3, 0, 0), pad_edge=False)
    table.add_column(style="bold")
    table.add_column(style=DIM)
    for name, desc in COMMANDS:
        table.add_row(name, desc)
    console.print(Padding(table, (1, 0, 1, 2)))


# ---------------------------------------------------------------- parsing


class _ParseError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _ParseError(message)


def make_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m rosetta", add_help=False)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("build").set_defaults(fn=cmd_build)
    p = sub.add_parser("find")
    p.add_argument("text", nargs="+")
    p.add_argument("--lang", choices=["zh", "en"])
    p.add_argument("-k", type=int, default=8)
    p.set_defaults(fn=cmd_find)
    for name, fn, k in (("equiv", cmd_equiv, 5), ("compare", cmd_compare, 6)):
        p = sub.add_parser(name)
        p.add_argument("idiom", nargs="+")
        p.add_argument("-k", type=int, default=k)
        p.set_defaults(fn=fn)
    sub.add_parser("add").set_defaults(fn=cmd_add)
    p = sub.add_parser("explain")
    p.add_argument("idiom", nargs="+")
    p.set_defaults(fn=cmd_explain)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    p = sub.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=cmd_serve)
    sub.add_parser("help").set_defaults(fn=cmd_help)
    return parser


def run(argv: list[str]) -> bool:
    """Run one command. Returns False when the shell should exit."""
    if not argv:
        return True
    if argv[0] in ("quit", "exit", "q"):
        return False
    try:
        args = make_parser().parse_args(argv)
    except _ParseError as e:
        console.print(f"[{DIM}]{e}. Type 'help' for commands.[/]")
        return True
    if args.command is None:
        cmd_help()
        return True
    needs_db = args.command not in ("build", "help", "serve")
    try:
        if needs_db and db.meaning().count() == 0:
            console.print("The database is empty. Run [bold]build[/] first.")
            return True
        args.fn(args)
    except db.ModelMismatch as e:
        console.print(str(e))
    return True


def banner() -> None:
    title = Text("Idiom Rosetta", style="bold")
    title.append("  画蛇添足 ≈ gild the lily", style=DIM)
    console.print(title)
    try:
        with console.status("Opening the database…", spinner="dots"):
            s = db.stats()
    except db.ModelMismatch as e:
        console.print(str(e))
        return
    if s["meaning"] == 0:
        console.print("No idioms stored yet. Run [bold]build[/] to fetch and embed both datasets.")
    else:
        console.print(
            f"{s['meaning']:,} idioms ([{LANG_STYLE['zh']}]{s['zh']:,} zh[/], "
            f"[{LANG_STYLE['en']}]{s['en']:,} en[/]). Type 'help' for commands."
        )


def shell() -> None:
    banner()
    while True:
        try:
            line = console.input("\n[bold #c8442f]rosetta›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        try:
            argv = shlex.split(line)
        except ValueError as e:
            console.print(f"[{DIM}]{e}[/]")
            continue
        try:
            if not run(argv):
                return
        except KeyboardInterrupt:
            console.print()
