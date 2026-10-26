"""`python -m rosetta` opens the shell; `python -m rosetta <command> …` runs one command."""

import os
import sys

# Keep library chatter (tokenizers fork warning, HF progress bars) out of the shell.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

from .cli import run, shell  # noqa: E402


def main() -> None:
    if len(sys.argv) > 1:
        run(sys.argv[1:])
    else:
        shell()


if __name__ == "__main__":
    main()
