import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from kanbox.cli import build_parser, main

FIXTURE = Path(__file__).parent / "fixtures" / "sample_board.json"
ASANA_FIXTURE = Path(__file__).parent / "fixtures" / "sample_asana_board.json"


class BuildParserTests(unittest.TestCase):
    def test_defaults(self):
        args = build_parser().parse_args([str(FIXTURE)])
        self.assertEqual(args.source, "trello")
        self.assertEqual(args.format, "markdown")
        self.assertIsNone(args.output)
        self.assertFalse(args.include_closed)

    def test_unknown_format_is_rejected(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([str(FIXTURE), "-f", "xml"])

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([str(FIXTURE), "-s", "jira"])


class MainTests(unittest.TestCase):
    def test_writes_markdown_to_stdout_by_default(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status = main([str(FIXTURE)])
        self.assertEqual(status, 0)
        self.assertTrue(buf.getvalue().startswith("# Sprint planning\n"))

    def test_asana_source_reaches_the_parser(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status = main([str(ASANA_FIXTURE), "--source", "asana"])
        self.assertEqual(status, 0)
        self.assertTrue(buf.getvalue().startswith("# Marketing launch\n"))

    def test_csv_format_goes_to_stdout(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status = main([str(FIXTURE), "--format", "csv"])
        self.assertEqual(status, 0)
        self.assertTrue(buf.getvalue().startswith("list,card,labels,due,closed,checklist,url"))

    def test_include_closed_flag_reaches_the_renderer(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main([str(FIXTURE), "--include-closed"])
        self.assertIn("~~Ship v1.2~~", buf.getvalue())

    def test_output_flag_writes_to_a_file_instead_of_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "board.md"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                status = main([str(FIXTURE), "-o", str(out_path)])
            self.assertEqual(status, 0)
            self.assertEqual(buf.getvalue(), "")
            self.assertTrue(out_path.read_text().startswith("# Sprint planning\n"))

    def test_missing_input_file_reports_error_and_exits_nonzero(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            status = main(["/no/such/file.json"])
        self.assertEqual(status, 1)
        self.assertIn("could not read", buf.getvalue())

    def test_invalid_json_reports_error_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "bad.json"
            bad_path.write_text("{not valid json")
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                status = main([str(bad_path)])
            self.assertEqual(status, 1)
            self.assertIn("could not read", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
