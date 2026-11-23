import io
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

    def test_no_agents_file_passes(self) -> None:
        code, out, err, runner = self.run_doctor()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, "No AGENTS.md in this repo, so CLAUDE.md needs no import.\n")
        self.assertEqual(runner.gh_calls(), [])

    def test_agents_file_without_claude_file_fails(self) -> None:
        (self.root / "AGENTS.md").write_text("# Agents\n")
        code, out, err, _ = self.run_doctor()
        self.assertEqual((code, out), (1, ""))
        self.assertIn("Create CLAUDE.md with the line `@AGENTS.md`.", err)

    def test_claude_file_without_the_import_fails(self) -> None:
        (self.root / "AGENTS.md").write_text("# Agents\n")
        (self.root / "CLAUDE.md").write_text("# Claude\n\nRead AGENTS.md. See @AGENTS.md for rules.\n@AGENTS.md.bak\n")
        code, out, err, _ = self.run_doctor()
        self.assertEqual((code, out), (1, ""))
        self.assertIn("CLAUDE.md has no line `@AGENTS.md`.", err)

    def test_import_line_with_surrounding_whitespace_passes(self) -> None:
        (self.root / "AGENTS.md").write_text("# Agents\n")
        (self.root / "CLAUDE.md").write_text("# Claude\n\n  @AGENTS.md \t\n\nMore rules.\n")
        code, out, err, _ = self.run_doctor()
        self.assertEqual((code, out, err), (0, "CLAUDE.md imports AGENTS.md.\n", ""))


if __name__ == "__main__":
    unittest.main()
