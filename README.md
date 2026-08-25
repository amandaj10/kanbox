# kanbox

Trello's "export as JSON" button gives you a huge, mostly-unreadable dump of
every field the API knows about. That's fine for re-importing into Trello,
but useless if you just want to keep a record of a board before archiving or
deleting it, or if you want to diff a board's state over time in git.

`kanbox` reads that JSON export and turns it into a plain markdown or CSV
snapshot: one section per list, one bullet per card, with labels, due dates,
and descriptions kept.

## Usage

Export a board from Trello (Menu -> Print, export, and share -> Export as
JSON) and run:

```
python -m kanbox board.json > board.md
```

```
$ python -m kanbox board.json
# Sprint planning

## Backlog

- Set up staging environment
  - labels: infra
- Write onboarding docs

## In progress

- Fix pagination bug
  - due: 2026-08-28T00:00:00.000Z
    > Users report the third page is missing on mobile.

## Done

- ~~Ship v1.2~~
```

CSV is useful if you want to load the board into a spreadsheet instead:

```
python -m kanbox board.json --format csv -o board.csv
```

Archived cards are skipped by default; pass `--include-closed` to keep them.

## Library

The CLI is a thin wrapper around three functions, which you can use directly
if you want to do something other than print markdown or CSV:

```python
import json
from kanbox import parse_trello_export, render_markdown

data = json.load(open("board.json"))
board = parse_trello_export(data)
print(render_markdown(board))
```

`parse_trello_export` returns a `Board` with a flat list of `Card` objects,
so it's also a reasonable starting point for writing your own exporter (say,
to a static site or a different task tracker's import format).

## Development

Tests use the standard library's `unittest` against fixture JSON under
`tests/fixtures/`, no test runner to install:

```
python -m unittest discover
```

## Status

Only Trello's export format is supported right now. No third-party
dependencies, standard library only.
