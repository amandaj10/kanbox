# kanbox

Trello's "export as JSON" button gives you a huge, mostly-unreadable dump of
every field the API knows about. That's fine for re-importing into Trello,
but useless if you just want to keep a record of a board before archiving or
deleting it, or if you want to diff a board's state over time in git.

`kanbox` reads that JSON export and turns it into a plain markdown or CSV
snapshot: one section per list, one bullet per card, with labels, due dates,
descriptions, and checklist items kept.

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
  - [x] Reproduce locally
  - [ ] Deploy fix

## Done

- ~~Ship v1.2~~
```

CSV is useful if you want to load the board into a spreadsheet instead. Each
card's checklist progress is collapsed into a single `checked/total` column
rather than one row per item:

```
python -m kanbox board.json --format csv -o board.csv
```

Archived cards are skipped by default; pass `--include-closed` to keep them.

Asana's project export is also supported -- pass `--source asana`:

```
python -m kanbox project.json --source asana --format csv -o project.csv
```

So is a Jira issue search export (the JSON you get back from the
`/rest/api/2/search` endpoint, saved to a file) -- pass `--source jira`:

```
python -m kanbox issues.json --source jira --format csv -o project.csv
```

## Library

The CLI is a thin wrapper around a parser and a renderer, which you can use
directly if you want to do something other than print markdown or CSV:

```python
import json
from kanbox import parse_trello_export, render_markdown

data = json.load(open("board.json"))
board = parse_trello_export(data)
print(render_markdown(board))
```

`parse_trello_export`, `parse_asana_export`, and `parse_jira_export` all
return the same `Board` of flat `Card` objects, so any one of them is a
reasonable starting point for writing your own exporter (say, to a static
site or a different task tracker's import format).

## Development

Tests use the standard library's `unittest` against fixture JSON under
`tests/fixtures/`, no test runner to install:

```
python -m unittest discover
```

## Status

Trello, Asana, and Jira export formats are supported so far, all feeding the
same `Board` model. No third-party dependencies, standard library only.
