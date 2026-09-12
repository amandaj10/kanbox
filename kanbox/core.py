"""Parse Trello's JSON export format and render it as plain text."""

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChecklistItem:
    name: str
    checked: bool = False


@dataclass
class Card:
    name: str
    list_name: str
    description: str = ""
    labels: list = field(default_factory=list)
    due: Optional[str] = None
    closed: bool = False
    url: str = ""
    checklist_items: list = field(default_factory=list)


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

    # Checklists live in their own top-level array, tied to a card by idCard,
    # each carrying its own checkItems. A card's checklists aren't kept
    # separate here -- their items are flattened onto the card in checklist
    # order, which matches the rest of this library's flat Card model.
    checklist_items_by_card = {}
    checklists = sorted(data.get("checklists", []), key=lambda cl: cl.get("pos", 0))
    for cl in checklists:
        items = sorted(cl.get("checkItems", []), key=lambda item: item.get("pos", 0))
        checklist_items_by_card.setdefault(cl.get("idCard"), []).extend(
            ChecklistItem(name=item.get("name", ""), checked=item.get("state") == "complete")
            for item in items
        )

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
                checklist_items=checklist_items_by_card.get(c.get("id"), []),
            )
        )

    return Board(name=data.get("name", "untitled board"), cards=cards, list_order=list_order)


def parse_asana_export(data: dict) -> Board:
    """Build a Board from Asana's project export (a project plus its tasks).

    Unlike Trello, a task's section and subtasks are already inline on the
    task rather than split across separate top-level arrays, so there's no
    id table to resolve first -- we just read section.name and subtasks
    straight off each task.
    """
    list_order = [s.get("name", "") for s in data.get("sections", [])]

    cards = []
    for t in data.get("tasks", []):
        section_name = "(no section)"
        memberships = t.get("memberships") or []
        if memberships:
            section = memberships[0].get("section") or {}
            section_name = section.get("name") or section_name
        if section_name not in list_order:
            list_order.append(section_name)

        tags = [tag.get("name", "") for tag in t.get("tags", [])]
        checklist_items = [
            ChecklistItem(name=sub.get("name", ""), checked=bool(sub.get("completed", False)))
            for sub in t.get("subtasks", [])
        ]

        cards.append(
            Card(
                name=t.get("name", ""),
                list_name=section_name,
                description=t.get("notes", ""),
                labels=[tag for tag in tags if tag],
                due=t.get("due_on") or t.get("due_at"),
                closed=bool(t.get("completed", False)),
                url=t.get("permalink_url", ""),
                checklist_items=checklist_items,
            )
        )

    return Board(name=data.get("name", "untitled board"), cards=cards, list_order=list_order)


def parse_jira_export(data: dict) -> Board:
    """Build a Board from a Jira issue search export (the REST API's
    /search response shape: a project plus a flat "issues" array).

    An issue's column is fields.status, not a separate id table like
    Trello's lists, so list_order is discovered from the order statuses
    are first seen -- the same approach the Asana parser uses for
    sections. fields.status.statusCategory.key is a fixed Jira
    vocabulary ("new", "indeterminate", "done"), which is a far more
    reliable "is this finished" signal than guessing from the
    human-editable status name, so that's what decides closed/checked
    rather than the name itself.
    """
    list_order = []
    cards = []

    def is_done(status):
        return (status or {}).get("statusCategory", {}).get("key") == "done"

    def browse_url(issue):
        match = re.match(r"https?://[^/]+", issue.get("self", ""))
        return f"{match.group(0)}/browse/{issue.get('key', '')}" if match else ""

    for issue in data.get("issues", []):
        fields = issue.get("fields", {})
        status = fields.get("status") or {}
        list_name = status.get("name", "(no status)")
        if list_name not in list_order:
            list_order.append(list_name)

        checklist_items = [
            ChecklistItem(
                name=sub.get("fields", {}).get("summary", ""),
                checked=is_done(sub.get("fields", {}).get("status")),
            )
            for sub in fields.get("subtasks", [])
        ]

        cards.append(
            Card(
                name=fields.get("summary", ""),
                list_name=list_name,
                description=fields.get("description") or "",
                labels=[label for label in fields.get("labels", []) if label],
                due=fields.get("duedate"),
                closed=is_done(status),
                url=browse_url(issue),
                checklist_items=checklist_items,
            )
        )

    project_name = data.get("project", {}).get("name")
    return Board(name=project_name or "untitled board", cards=cards, list_order=list_order)


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
            for item in card.checklist_items:
                box = "x" if item.checked else " "
                lines.append(f"  - [{box}] {item.name}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_csv(board: Board, include_closed: bool = False) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["list", "card", "labels", "due", "closed", "checklist", "url"])
    for card in board.cards:
        if card.closed and not include_closed:
            continue
        if card.checklist_items:
            checked = sum(1 for item in card.checklist_items if item.checked)
            checklist = f"{checked}/{len(card.checklist_items)}"
        else:
            checklist = ""
        writer.writerow(
            [
                card.list_name,
                card.name,
                "; ".join(card.labels),
                card.due or "",
                "yes" if card.closed else "no",
                checklist,
                card.url,
            ]
        )
    return buf.getvalue()
