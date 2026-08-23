"""Parse Trello's JSON export format and render it as plain text."""

import csv
import io
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Card:
    name: str
    list_name: str
    description: str = ""
    labels: list = field(default_factory=list)
    due: Optional[str] = None
    closed: bool = False
    url: str = ""


@dataclass
class Board:
    name: str
    cards: list = field(default_factory=list)
    list_order: list = field(default_factory=list)


def parse_trello_export(data: dict) -> Board:
    """Build a Board from the dict you get by loading Trello's JSON export.

    Trello only gives you list membership as an id (idList) pointing into
    the top-level "lists" array, so we resolve that once up front instead
    of carrying ids through the rest of the library.
    """
    lists_by_id = {}
    list_order = []
    for lst in data.get("lists", []):
        lists_by_id[lst["id"]] = lst["name"]
        list_order.append(lst["name"])

    cards = []
    for c in data.get("cards", []):
        list_name = lists_by_id.get(c.get("idList"), "(unknown list)")
        labels = [lbl.get("name") or lbl.get("color", "") for lbl in c.get("labels", [])]
        cards.append(
            Card(
                name=c.get("name", ""),
                list_name=list_name,
                description=c.get("desc", ""),
                labels=[label for label in labels if label],
                due=c.get("due"),
                closed=bool(c.get("closed", False)),
                url=c.get("shortUrl") or c.get("url", ""),
            )
        )

    return Board(name=data.get("name", "untitled board"), cards=cards, list_order=list_order)


def render_markdown(board: Board, include_closed: bool = False) -> str:
    lines = [f"# {board.name}", ""]

    cards_by_list = {name: [] for name in board.list_order}
    for card in board.cards:
        cards_by_list.setdefault(card.list_name, []).append(card)

    for list_name, all_cards in cards_by_list.items():
        cards = [c for c in all_cards if include_closed or not c.closed]
        if not cards:
            continue

        lines.append(f"## {list_name}")
        lines.append("")
        for card in cards:
            marker = "~~" if card.closed else ""
            lines.append(f"- {marker}{card.name}{marker}")
            if card.labels:
                lines.append(f"  - labels: {', '.join(card.labels)}")
            if card.due:
                lines.append(f"  - due: {card.due}")
            if card.description:
                indented = card.description.strip().replace("\n", "\n    ")
                lines.append(f"    > {indented}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_csv(board: Board, include_closed: bool = False) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["list", "card", "labels", "due", "closed", "url"])
    for card in board.cards:
        if card.closed and not include_closed:
            continue
        writer.writerow(
            [
                card.list_name,
                card.name,
                "; ".join(card.labels),
                card.due or "",
                "yes" if card.closed else "no",
                card.url,
            ]
        )
    return buf.getvalue()
