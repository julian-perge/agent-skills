import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_skills import cli
from fakes import FakeRunner


class DoctorVerbTest(unittest.TestCase):
    def setUp(self) -> None:
        self.checkout = tempfile.TemporaryDirectory()
        self.addCleanup(self.checkout.cleanup)
        self.root = Path(self.checkout.name)

    def run_doctor(self) -> tuple[int, str, str, FakeRunner]:
        runner = FakeRunner().on("git", "rev-parse", "--show-toplevel", stdout=self.checkout.name + "\n")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["doctor"], runner)
        return code, out.getvalue(), err.getvalue(), runner

    def write(self, name: str, text: str | bytes) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode() if isinstance(text, str) else text)

    def assert_passes(self, claude_text: str | bytes, name: str = "CLAUDE.md") -> None:
        self.write("AGENTS.md", "# Agents\n")
        self.write(name, claude_text)
        code, out, err, _ = self.run_doctor()
        self.assertEqual((code, out, err), (0, f"{name} imports AGENTS.md.\n", ""))

    def assert_fails(self, claude_text: str | bytes) -> str:
        self.write("AGENTS.md", "# Agents\n")
        self.write("CLAUDE.md", claude_text)
        code, out, err, _ = self.run_doctor()
        self.assertEqual((code, out), (1, ""))
        return err

    def test_no_agents_file_passes(self) -> None:
        code, out, err, runner = self.run_doctor()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, "No AGENTS.md in this repo, so CLAUDE.md needs no import.\n")
        self.assertEqual(runner.gh_calls(), [])

    def test_agents_file_without_claude_file_passes_with_a_note(self) -> None:
        self.write("AGENTS.md", "# Agents\n")
        code, out, err, _ = self.run_doctor()
        self.assertEqual((code, out, err), (0, "No CLAUDE.md in this repo, so Claude Code reads AGENTS.md itself.\n", ""))

    def test_claude_local_file_alone_fails(self) -> None:
        self.write("AGENTS.md", "# Agents\n")
        self.write("CLAUDE.local.md", "# Mine\n")
        code, out, err, _ = self.run_doctor()
        self.assertEqual((code, out), (1, ""))
        self.assertIn("Create CLAUDE.md with the line `@AGENTS.md`.", err)

    def test_claude_file_without_the_import_fails(self) -> None:
        err = self.assert_fails("# Claude\n\nRead AGENTS.md.\n@AGENTS.md.bak\n@/AGENTS.md\nmail@AGENTS.md\n")
        self.assertIn("CLAUDE.md does not import AGENTS.md. When CLAUDE.md exists, Claude Code reads it instead of AGENTS.md", err)
        self.assertIn("Add the line `@AGENTS.md` to CLAUDE.md", err)

    def test_import_line_with_surrounding_whitespace_passes(self) -> None:
        self.assert_passes("# Claude\n\n  @AGENTS.md \t\n\nMore rules.\n")

    def test_inline_import_passes(self) -> None:
        self.assert_passes("# Claude\n\nSee @AGENTS.md for rules.\n")

    def test_dot_slash_import_passes(self) -> None:
        self.assert_passes("@./AGENTS.md\n")

    def test_import_after_a_byte_order_mark_passes(self) -> None:
        self.assert_passes(b"\xef\xbb\xbf@AGENTS.md\n")

    def test_crlf_line_ends_pass(self) -> None:
        self.assert_passes(b"# Claude\r\n@AGENTS.md\r\n")

    def test_import_in_a_fenced_code_block_fails(self) -> None:
        self.assert_fails("# Claude\n\n```\n@AGENTS.md\n```\n")
        self.assert_fails("# Claude\n\n~~~~ markdown\n@AGENTS.md\n~~~\n~~~~\n")

    def test_import_after_a_closed_code_block_passes(self) -> None:
        self.assert_passes("```\nls\n```\n@AGENTS.md\n")

    def test_import_in_an_html_comment_fails(self) -> None:
        self.assert_fails("<!-- @AGENTS.md -->\n")
        self.assert_fails("<!--\n@AGENTS.md\n-->\n")

    def test_import_next_to_an_html_comment_passes(self) -> None:
        self.assert_passes("<!-- note --> @AGENTS.md\n")
        self.assert_passes("<!--\nnote\n--> @AGENTS.md\n")

    def test_import_in_a_code_span_fails(self) -> None:
        self.assert_fails("Add the line `@AGENTS.md` to CLAUDE.md.\n")
        self.assert_fails("Add `` @AGENTS.md `` here.\n")

    def test_claude_link_to_agents_file_passes(self) -> None:
        self.write("AGENTS.md", "# Agents\n")
        (self.root / "CLAUDE.md").symlink_to("AGENTS.md")
        code, out, err, _ = self.run_doctor()
        self.assertEqual((code, out, err), (0, "CLAUDE.md is a link to AGENTS.md, so Claude Code reads AGENTS.md.\n", ""))

    def test_claude_link_to_another_file_without_the_import_fails(self) -> None:
        self.write("OTHER.md", "# Other\n")
        (self.root / "CLAUDE.md").symlink_to("OTHER.md")
        self.write("AGENTS.md", "# Agents\n")
        code, out, _, _ = self.run_doctor()
        self.assertEqual((code, out), (1, ""))

    def test_dot_claude_file_with_parent_import_passes(self) -> None:
        self.assert_passes("@../AGENTS.md\n", ".claude/CLAUDE.md")

    def test_dot_claude_file_with_a_root_relative_import_fails(self) -> None:
        self.write("AGENTS.md", "# Agents\n")
        self.write(".claude/CLAUDE.md", "@AGENTS.md\n")
        code, out, err, _ = self.run_doctor()
        self.assertEqual((code, out), (1, ""))
        self.assertIn("Add the line `@../AGENTS.md` to .claude/CLAUDE.md", err)

    def test_dot_claude_file_link_to_agents_file_passes(self) -> None:
        self.write("AGENTS.md", "# Agents\n")
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "CLAUDE.md").symlink_to("../AGENTS.md")
        code, out, err, _ = self.run_doctor()
        self.assertEqual((code, out, err), (0, ".claude/CLAUDE.md is a link to AGENTS.md, so Claude Code reads AGENTS.md.\n", ""))

    def test_import_in_either_claude_file_passes(self) -> None:
        self.write("CLAUDE.md", "# Claude\n")
        self.assert_passes("@../AGENTS.md\n", ".claude/CLAUDE.md")

    def test_both_claude_files_without_the_import_fail(self) -> None:
        self.write(".claude/CLAUDE.md", "# More\n")
        err = self.assert_fails("# Claude\n")
        self.assertIn("CLAUDE.md and .claude/CLAUDE.md do not import AGENTS.md.", err)
        self.assertIn("Add the line `@AGENTS.md` to CLAUDE.md", err)

    def test_claude_file_that_is_not_utf8_is_an_environment_error(self) -> None:
        self.write("AGENTS.md", "# Agents\n")
        self.write("CLAUDE.md", b"# Caf\xe9\n@AGENTS.md\n")
        code, out, err, _ = self.run_doctor()
        self.assertEqual((code, out), (2, ""))
        self.assertIn(f"{self.root / 'CLAUDE.md'} is not UTF-8 text", err)
        self.assertNotIn("Traceback", err)

    def test_run_from_a_subdirectory_checks_the_checkout_root(self) -> None:
        (self.root / "sub").mkdir()
        here = os.getcwd()
        os.chdir(self.root / "sub")
        self.addCleanup(os.chdir, here)
        self.assert_passes("@AGENTS.md\n")


if __name__ == "__main__":
    unittest.main()
