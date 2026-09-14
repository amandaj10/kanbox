import argparse
import json
import sys
from pathlib import Path

from .core import (
    diff_boards,
    parse_asana_export,
    parse_jira_export,
    parse_trello_export,
    render_csv,
    render_diff,
    render_markdown,
)

RENDERERS = {
    "markdown": render_markdown,
    "csv": render_csv,
}

PARSERS = {
    "trello": parse_trello_export,
    "asana": parse_asana_export,
    "jira": parse_jira_export,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kanbox",
        description="Convert a Trello, Asana, or Jira JSON export into a plain-text snapshot.",
    )
    parser.add_argument("input", type=Path, help="path to a board export")
    parser.add_argument(
        "-s",
        "--source",
        choices=sorted(PARSERS),
        default="trello",
        help="export format to read (default: trello)",
    )
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
    parser.add_argument(
        "--diff",
        type=Path,
        metavar="OLDER",
        default=None,
        help=(
            "compare an earlier export (OLDER) against the input and print "
            "what changed, instead of rendering a snapshot"
        ),
    )
    return parser


def _load_json(path: Path):
    return json.loads(path.read_text())


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    parse = PARSERS[args.source]

    try:
        board = parse(_load_json(args.input))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"kanbox: could not read {args.input}: {exc}", file=sys.stderr)
        return 1

    if args.diff:
        try:
            older_board = parse(_load_json(args.diff))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"kanbox: could not read {args.diff}: {exc}", file=sys.stderr)
            return 1
        output = render_diff(diff_boards(older_board, board))
    else:
        render = RENDERERS[args.format]
        output = render(board, include_closed=args.include_closed)

    if args.output:
        args.output.write_text(output)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
