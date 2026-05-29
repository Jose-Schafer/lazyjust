import argparse
from pathlib import Path

from lib.app import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Lazy-style TUI for monorepo justfiles.")
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Project root containing the justfile. Defaults to the current directory.",
    )
    args = parser.parse_args()
    return run(Path(args.root).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
