import argparse
import json
import sys
from pathlib import Path

from .core import parse_trello_export, render_csv, render_markdown

RENDERERS = {
    "markdown": render_markdown,
    "csv": render_csv,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kanbox",
        description="Convert a Trello JSON export into a plain-text snapshot.",
    )
    parser.add_argument("input", type=Path, help="path to a Trello JSON export")
    parser.add_argument(
        "-f",
        "--format",
        choices=sorted(RENDERERS),
        default="markdown",
        help="output format (default: markdown)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="write to this file instead of stdout",
    )
    parser.add_argument(
        "--include-closed",
        action="store_true",
        help="include archived lists/cards in the output",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        data = json.loads(args.input.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"kanbox: could not read {args.input}: {exc}", file=sys.stderr)
        return 1

    board = parse_trello_export(data)
    render = RENDERERS[args.format]
    output = render(board, include_closed=args.include_closed)

    if args.output:
        args.output.write_text(output)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
