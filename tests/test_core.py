import csv
import io
import json
import unittest
from pathlib import Path

from kanbox.core import (
    ChecklistItem,
    diff_boards,
    parse_asana_export,
    parse_jira_export,
    parse_trello_export,
    render_csv,
    render_diff,
    render_markdown,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_board.json"
BEFORE_FIXTURE = Path(__file__).parent / "fixtures" / "sample_board_before.json"
ASANA_FIXTURE = Path(__file__).parent / "fixtures" / "sample_asana_board.json"
JIRA_FIXTURE = Path(__file__).parent / "fixtures" / "sample_jira_board.json"


def load_board():
    data = json.loads(FIXTURE.read_text())
    return parse_trello_export(data)


def load_before_board():
    data = json.loads(BEFORE_FIXTURE.read_text())
    return parse_trello_export(data)


def load_asana_board():
    data = json.loads(ASANA_FIXTURE.read_text())
    return parse_asana_export(data)


def load_jira_board():
    data = json.loads(JIRA_FIXTURE.read_text())
    return parse_jira_export(data)


class ParseTrelloExportTests(unittest.TestCase):
    def setUp(self):
        self.board = load_board()

    def test_board_name_and_list_order(self):
        self.assertEqual(self.board.name, "Sprint planning")
        self.assertEqual(
            self.board.list_order, ["Backlog", "In progress", "Done", "Blocked"]
        )

    def test_card_count(self):
        self.assertEqual(len(self.board.cards), 5)

    def test_label_falls_back_to_color_when_name_is_blank(self):
        card = next(c for c in self.board.cards if c.name == "Fix pagination bug")
        self.assertEqual(card.labels, ["red"])

    def test_label_dropped_when_name_and_color_both_blank(self):
        card = next(c for c in self.board.cards if c.name == "Ship v1.2")
        self.assertEqual(card.labels, [])

    def test_card_with_unknown_idlist_gets_placeholder(self):
        card = next(c for c in self.board.cards if c.name.startswith("Orphaned"))
        self.assertEqual(card.list_name, "(unknown list)")

    def test_url_falls_back_when_shorturl_missing(self):
        card = next(c for c in self.board.cards if c.name.startswith("Orphaned"))
        self.assertEqual(card.url, "https://trello.com/c/card5/long-form-url")

    def test_closed_flag_is_read(self):
        card = next(c for c in self.board.cards if c.name == "Ship v1.2")
        self.assertTrue(card.closed)

    def test_untitled_board_when_name_missing(self):
        board = parse_trello_export({"lists": [], "cards": []})
        self.assertEqual(board.name, "untitled board")

    def test_checklist_items_are_attached_to_their_card_in_pos_order(self):
        card = next(c for c in self.board.cards if c.name == "Fix pagination bug")
        self.assertEqual(
            card.checklist_items,
            [
                ChecklistItem(name="Reproduce locally", checked=True),
                ChecklistItem(name="Deploy fix", checked=False),
            ],
        )

    def test_card_without_checklist_has_empty_list(self):
        card = next(c for c in self.board.cards if c.name == "Ship v1.2")
        self.assertEqual(card.checklist_items, [])


class ParseAsanaExportTests(unittest.TestCase):
    def setUp(self):
        self.board = load_asana_board()

    def test_board_name_and_list_order(self):
        self.assertEqual(self.board.name, "Marketing launch")
        self.assertEqual(
            self.board.list_order,
            ["To do", "Doing", "Done", "(no section)"],
        )

    def test_card_count(self):
        self.assertEqual(len(self.board.cards), 5)

    def test_section_name_is_read_straight_off_the_membership(self):
        card = next(c for c in self.board.cards if c.name == "Fix tracking pixel")
        self.assertEqual(card.list_name, "Doing")

    def test_task_with_no_membership_gets_placeholder(self):
        card = next(c for c in self.board.cards if c.name.startswith("Orphaned"))
        self.assertEqual(card.list_name, "(no section)")

    def test_blank_tag_name_is_dropped(self):
        card = next(c for c in self.board.cards if c.name == "Brief the design team")
        self.assertEqual(card.labels, [])

    def test_completed_flag_is_read(self):
        card = next(c for c in self.board.cards if c.name == "Launch announcement email")
        self.assertTrue(card.closed)

    def test_untitled_board_when_name_missing(self):
        board = parse_asana_export({"sections": [], "tasks": []})
        self.assertEqual(board.name, "untitled board")

    def test_subtasks_become_checklist_items_in_order(self):
        card = next(c for c in self.board.cards if c.name == "Fix tracking pixel")
        self.assertEqual(
            card.checklist_items,
            [
                ChecklistItem(name="Reproduce in Safari", checked=True),
                ChecklistItem(name="Ship fix", checked=False),
            ],
        )

    def test_task_without_subtasks_has_empty_checklist(self):
        card = next(c for c in self.board.cards if c.name == "Draft landing page copy")
        self.assertEqual(card.checklist_items, [])

    def test_renders_with_the_same_markdown_renderer(self):
        output = render_markdown(self.board)
        self.assertIn("## To do", output)
        self.assertIn("- Draft landing page copy", output)
        self.assertIn("  - [x] Reproduce in Safari", output)
        self.assertNotIn("Launch announcement email", output)


class ParseJiraExportTests(unittest.TestCase):
    def setUp(self):
        self.board = load_jira_board()

    def test_board_name_comes_from_project(self):
        self.assertEqual(self.board.name, "Platform")

    def test_list_order_follows_first_appearance_of_each_status(self):
        self.assertEqual(
            self.board.list_order, ["To Do", "In Progress", "Done", "Blocked"]
        )

    def test_card_count(self):
        self.assertEqual(len(self.board.cards), 5)

    def test_blank_label_is_dropped(self):
        card = next(c for c in self.board.cards if c.name == "Write onboarding docs")
        self.assertEqual(card.labels, [])

    def test_label_is_kept(self):
        card = next(c for c in self.board.cards if c.name == "Set up staging environment")
        self.assertEqual(card.labels, ["infra"])

    def test_done_status_category_marks_card_closed(self):
        card = next(c for c in self.board.cards if c.name == "Ship v1.2")
        self.assertTrue(card.closed)

    def test_non_done_status_category_leaves_card_open(self):
        card = next(c for c in self.board.cards if c.name == "Set up staging environment")
        self.assertFalse(card.closed)

    def test_browse_url_is_built_from_the_self_link(self):
        card = next(c for c in self.board.cards if c.name == "Fix pagination bug")
        self.assertEqual(card.url, "https://example.atlassian.net/browse/PLAT-103")

    def test_url_is_blank_when_self_link_is_unparsable(self):
        card = next(c for c in self.board.cards if c.name == "Card with unparsable self link")
        self.assertEqual(card.url, "")

    def test_subtasks_become_checklist_items_using_status_category(self):
        card = next(c for c in self.board.cards if c.name == "Fix pagination bug")
        self.assertEqual(
            card.checklist_items,
            [
                ChecklistItem(name="Reproduce locally", checked=True),
                ChecklistItem(name="Deploy fix", checked=False),
            ],
        )

    def test_untitled_board_when_project_missing(self):
        board = parse_jira_export({"issues": []})
        self.assertEqual(board.name, "untitled board")

    def test_renders_with_the_same_markdown_renderer(self):
        output = render_markdown(self.board)
        self.assertIn("## To Do", output)
        self.assertIn("- Set up staging environment", output)
        self.assertIn("  - [x] Reproduce locally", output)
        self.assertNotIn("Ship v1.2", output)


class RenderMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.board = load_board()

    def test_default_output_skips_closed_cards_and_empty_lists(self):
        output = render_markdown(self.board)
        expected = (
            "# Sprint planning\n"
            "\n"
            "## Backlog\n"
            "\n"
            "- Set up staging environment\n"
            "  - labels: infra\n"
            "- Write onboarding docs\n"
            "\n"
            "## In progress\n"
            "\n"
            "- Fix pagination bug\n"
            "  - labels: red\n"
            "  - due: 2026-08-28T00:00:00.000Z\n"
            "    > Users report the third page is missing on mobile.\n"
            "  - [x] Reproduce locally\n"
            "  - [ ] Deploy fix\n"
            "\n"
            "## (unknown list)\n"
            "\n"
            "- Orphaned card from a deleted list\n"
        )
        self.assertEqual(output, expected)
        self.assertNotIn("Done", output)
        self.assertNotIn("Blocked", output)

    def test_include_closed_shows_struck_through_card(self):
        output = render_markdown(self.board, include_closed=True)
        self.assertIn("## Done", output)
        self.assertIn("- ~~Ship v1.2~~", output)


class RenderCsvTests(unittest.TestCase):
    def setUp(self):
        self.board = load_board()

    def _rows(self, text):
        return list(csv.reader(io.StringIO(text)))

    def test_default_output_skips_closed_cards(self):
        rows = self._rows(render_csv(self.board))
        self.assertEqual(
            rows[0], ["list", "card", "labels", "due", "closed", "checklist", "url"]
        )
        self.assertEqual(len(rows), 5)  # header + 4 non-closed cards
        self.assertNotIn("Ship v1.2", [row[1] for row in rows])

    def test_include_closed_marks_card_as_yes(self):
        rows = self._rows(render_csv(self.board, include_closed=True))
        closed_row = next(row for row in rows if row[1] == "Ship v1.2")
        self.assertEqual(closed_row[4], "yes")

    def test_row_fields_for_a_regular_card(self):
        rows = self._rows(render_csv(self.board))
        row = next(row for row in rows if row[1] == "Fix pagination bug")
        self.assertEqual(
            row,
            [
                "In progress",
                "Fix pagination bug",
                "red",
                "2026-08-28T00:00:00.000Z",
                "no",
                "1/2",
                "https://trello.com/c/card3",
            ],
        )

    def test_checklist_column_blank_when_card_has_no_checklist(self):
        rows = self._rows(render_csv(self.board))
        row = next(row for row in rows if row[1] == "Write onboarding docs")
        self.assertEqual(row[5], "")


class DiffBoardsTests(unittest.TestCase):
    def setUp(self):
        self.diff = diff_boards(load_before_board(), load_board())

    def test_card_only_in_new_snapshot_is_added(self):
        self.assertEqual(
            [c.name for c in self.diff.added], ["Orphaned card from a deleted list"]
        )

    def test_card_only_in_old_snapshot_is_removed(self):
        self.assertEqual(
            [c.name for c in self.diff.removed], ["Retire the old staging box"]
        )

    def test_unchanged_card_is_not_reported(self):
        changed_names = [new.name for _old, new in self.diff.changed]
        self.assertNotIn("Set up staging environment", changed_names)

    def test_card_with_multiple_field_changes_is_reported_once(self):
        old_card, new_card = next(
            (o, n) for o, n in self.diff.changed if n.name == "Fix pagination bug"
        )
        self.assertEqual(old_card.list_name, "Backlog")
        self.assertEqual(new_card.list_name, "In progress")
        self.assertEqual(new_card.due, "2026-08-28T00:00:00.000Z")

    def test_closed_flag_change_is_reported(self):
        old_card, new_card = next(
            (o, n) for o, n in self.diff.changed if n.name == "Ship v1.2"
        )
        self.assertFalse(old_card.closed)
        self.assertTrue(new_card.closed)

    def test_card_with_no_matching_url_falls_back_to_list_and_name(self):
        old = parse_trello_export(
            {
                "lists": [{"id": "l1", "name": "Backlog"}],
                "cards": [{"id": "c1", "name": "No url card", "idList": "l1"}],
            }
        )
        new = parse_trello_export(
            {
                "lists": [{"id": "l1", "name": "Backlog"}],
                "cards": [
                    {
                        "id": "c1",
                        "name": "No url card",
                        "idList": "l1",
                        "desc": "now has a description",
                    }
                ],
            }
        )
        diff = diff_boards(old, new)
        self.assertEqual(len(diff.changed), 1)
        self.assertEqual(diff.added, [])
        self.assertEqual(diff.removed, [])


class RenderDiffTests(unittest.TestCase):
    def setUp(self):
        self.output = render_diff(diff_boards(load_before_board(), load_board()))

    def test_header_uses_new_boards_name(self):
        self.assertTrue(self.output.startswith("# Sprint planning (diff)\n"))

    def test_added_and_removed_sections_present(self):
        self.assertIn("## Added", self.output)
        self.assertIn("- Orphaned card from a deleted list", self.output)
        self.assertIn("## Removed", self.output)
        self.assertIn("- Retire the old staging box", self.output)

    def test_changed_section_lists_each_kind_of_field_change(self):
        self.assertIn("## Changed", self.output)
        self.assertIn("- Fix pagination bug", self.output)
        self.assertIn("  - moved: Backlog -> In progress", self.output)
        self.assertIn("  - due: (none) -> 2026-08-28T00:00:00.000Z", self.output)
        self.assertIn("  - labels: (none) -> red", self.output)
        self.assertIn("  - checklist: 0/2 -> 1/2", self.output)
        self.assertIn("- Ship v1.2", self.output)
        self.assertIn("  - open -> closed", self.output)

    def test_no_changes_reports_that_plainly(self):
        board = load_board()
        output = render_diff(diff_boards(board, board))
        self.assertEqual(output, "# Sprint planning (diff)\n\nNo changes.\n")


if __name__ == "__main__":
    unittest.main()
