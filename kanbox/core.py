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


@dataclass
class BoardDiff:
    board_name: str
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    changed: list = field(default_factory=list)


def _card_key(card: Card) -> str:
    """Identify the "same" card across two snapshots.

    A card's Trello/Asana/Jira id never makes it onto the Card model --
    render_markdown and render_csv never needed it -- but url is stable
    across edits, renames, and list moves, so it's the best identity
    available here. The rare card with no url (blank in all three parsers)
    falls back to list + name, which won't catch a rename but won't raise
    either.
    """
    return card.url or f"{card.list_name}\x00{card.name}"


def _card_fields(card: Card) -> tuple:
    return (
        card.list_name,
        card.description,
        tuple(card.labels),
        card.due,
        card.closed,
        tuple((item.name, item.checked) for item in card.checklist_items),
    )


def diff_boards(old: Board, new: Board) -> BoardDiff:
    """Compare two snapshots of the same board and report what changed.

    Meant for two exports of the same board taken at different times, not
    for comparing unrelated boards -- there's no cross-board card identity
    to match on.
    """
    old_by_key = {_card_key(c): c for c in old.cards}
    new_by_key = {_card_key(c): c for c in new.cards}

    diff = BoardDiff(board_name=new.name)
    for key, card in new_by_key.items():
        if key not in old_by_key:
            diff.added.append(card)
    for key, card in old_by_key.items():
        if key not in new_by_key:
            diff.removed.append(card)
    for key, new_card in new_by_key.items():
        old_card = old_by_key.get(key)
        if old_card is not None and _card_fields(old_card) != _card_fields(new_card):
            diff.changed.append((old_card, new_card))
    return diff


def render_diff(diff: BoardDiff) -> str:
    lines = [f"# {diff.board_name} (diff)", ""]

    if diff.added:
        lines.append("## Added")
        lines.append("")
        for card in diff.added:
            lines.append(f"- {card.name} ({card.list_name})")
        lines.append("")

    if diff.removed:
        lines.append("## Removed")
        lines.append("")
        for card in diff.removed:
            lines.append(f"- {card.name} ({card.list_name})")
        lines.append("")

    if diff.changed:
        lines.append("## Changed")
        lines.append("")
        for old_card, new_card in diff.changed:
            lines.append(f"- {new_card.name}")
            if old_card.list_name != new_card.list_name:
                lines.append(f"  - moved: {old_card.list_name} -> {new_card.list_name}")
            if old_card.closed != new_card.closed:
                was = "closed" if old_card.closed else "open"
                now = "closed" if new_card.closed else "open"
                lines.append(f"  - {was} -> {now}")
            if old_card.due != new_card.due:
                lines.append(f"  - due: {old_card.due or '(none)'} -> {new_card.due or '(none)'}")
            if old_card.labels != new_card.labels:
                old_labels = ", ".join(old_card.labels) or "(none)"
                new_labels = ", ".join(new_card.labels) or "(none)"
                lines.append(f"  - labels: {old_labels} -> {new_labels}")
            if old_card.description != new_card.description:
                lines.append("  - description changed")
            if old_card.checklist_items != new_card.checklist_items:
                old_done = sum(1 for i in old_card.checklist_items if i.checked)
                new_done = sum(1 for i in new_card.checklist_items if i.checked)
                lines.append(
                    f"  - checklist: {old_done}/{len(old_card.checklist_items)} "
                    f"-> {new_done}/{len(new_card.checklist_items)}"
                )
        lines.append("")

    if not (diff.added or diff.removed or diff.changed):
        lines.append("No changes.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


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
