import io
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from agent_skills import cli, run
from fakes import FakeRunner

PYTHON = sys.executable
LAUNCHER = Path(__file__).resolve().parents[3] / "bin" / "agent-skills"


def in_repo(top: str = "/Users/someone/code/blender-addon") -> FakeRunner:
    return FakeRunner().on("git", "rev-parse", "--show-toplevel", stdout=top + "\n")


class TmpdirCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"TMPDIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *argv: str, runner: FakeRunner | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["run", *argv], runner=runner or in_repo())
        return code, out.getvalue(), err.getvalue()

    def log_of(self, output: str) -> Path:
        first = output.splitlines()[0]
        self.assertTrue(first.startswith("log: "), first)
        return Path(first.removeprefix("log: "))


class ExitCodeTest(TmpdirCase):
    def test_exit_codes_pass_through(self) -> None:
        for wanted in (0, 1, 3):
            with self.subTest(code=wanted):
                code, out, _ = self.run_cli("--", PYTHON, "-c", f"raise SystemExit({wanted})")
                self.assertEqual(code, wanted)
                self.assertIn(f"exit {wanted} after ", out)

    def test_missing_command_is_127(self) -> None:
        code, out, err = self.run_cli("--", "no-such-command-agent-skills")
        self.assertEqual(code, 127)
        self.assertIn("command not found: no-such-command-agent-skills", err)
        self.assertIn("exit 127 after ", out)

    def test_signal_gives_128_plus_signal(self) -> None:
        code, out, _ = self.run_cli("--", PYTHON, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)")
        self.assertEqual(code, 143)
        self.assertIn("exit 143 after ", out)

    def test_no_command_is_a_usage_error(self) -> None:
        for argv in ((), ("--",), ("--name", "x")):
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual(code, 125)
                self.assertEqual(out, "")
                self.assertIn("no command", err)

    def test_bad_tail_is_a_usage_error(self) -> None:
        code, _, err = self.run_cli("--tail", "many", "--", "true")
        self.assertEqual(code, 125)
        self.assertIn("--tail", err)

    def test_command_runs_without_a_shell(self) -> None:
        code, out, _ = self.run_cli("--", PYTHON, "-c", "import sys; print(sys.argv[1:])", "$HOME", "a b")
        self.assertEqual(code, 0)
        self.assertIn("['$HOME', 'a b']", out)


class LogTest(TmpdirCase):
    def test_log_path_comes_first_and_names_repo_and_label(self) -> None:
        code, out, _ = self.run_cli("--name", "Unit Tests", "--", "true")
        self.assertEqual(code, 0)
        log = self.log_of(out)
        self.assertEqual(log.parent, Path(self.tmp.name) / "agent-skills" / "runs" / "blender-addon")
        self.assertRegex(log.name, r"^\d{8}-\d{6}-unit-tests\.log$")
        self.assertTrue(log.is_file())

    def test_outside_a_repo_the_folder_is_norepo(self) -> None:
        runner = FakeRunner().on("git", "rev-parse", "--show-toplevel", returncode=128, stderr="fatal: not a git repository")
        _, out, _ = self.run_cli("--", "true", runner=runner)
        self.assertEqual(self.log_of(out).parent.name, "norepo")

    def test_log_is_ansi_free_merged_and_in_order(self) -> None:
        script = "import sys; print('\\x1b[31mred\\x1b[0m', flush=True); print('to stderr', file=sys.stderr, flush=True); print('last')"
        _, out, _ = self.run_cli("--", PYTHON, "-c", script)
        self.assertEqual(self.log_of(out).read_text().splitlines(), ["red", "to stderr", "last"])

    def test_carriage_return_keeps_the_last_segment(self) -> None:
        _, out, _ = self.run_cli("--", PYTHON, "-c", "print('10%\\r50%\\rdone')")
        self.assertEqual(self.log_of(out).read_text().splitlines(), ["done"])

    def test_two_runs_in_one_second_get_two_logs(self) -> None:
        _, first, _ = self.run_cli("--name", "same", "--", "true")
        _, second, _ = self.run_cli("--name", "same", "--", "true")
        self.assertNotEqual(self.log_of(first), self.log_of(second))

    def test_log_can_be_read_while_the_command_runs(self) -> None:
        script = "import time; print('first', flush=True); time.sleep(1.5); print('second', flush=True)"
        wrapper = subprocess.Popen([PYTHON, str(LAUNCHER), "run", "--", PYTHON, "-c", script], stdout=subprocess.PIPE, text=True)
        try:
            assert wrapper.stdout is not None
            log = self.log_of(wrapper.stdout.readline())
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and "first" not in (log.read_text() if log.exists() else ""):
                time.sleep(0.02)
            self.assertIsNone(wrapper.poll(), "the command ended before the log was read")
            self.assertEqual(log.read_text().splitlines(), ["first"])
        finally:
            wrapper.communicate(timeout=10)
        self.assertEqual(wrapper.returncode, 0)
        self.assertEqual(log.read_text().splitlines(), ["first", "second"])

    def test_signal_reaches_the_command(self) -> None:
        script = "import signal, sys, time; signal.signal(signal.SIGTERM, lambda *a: sys.exit(7)); print('ready', flush=True); time.sleep(10)"
        wrapper = subprocess.Popen([PYTHON, str(LAUNCHER), "run", "--", PYTHON, "-c", script], stdout=subprocess.PIPE, text=True)
        assert wrapper.stdout is not None
        log = self.log_of(wrapper.stdout.readline())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "ready" not in (log.read_text() if log.exists() else ""):
            time.sleep(0.02)
        wrapper.send_signal(signal.SIGTERM)
        out, _ = wrapper.communicate(timeout=10)
        self.assertEqual(wrapper.returncode, 7)
        self.assertIn("exit 7 after ", out)


class OutputTest(TmpdirCase):
    def test_long_passing_run_prints_under_60_lines(self) -> None:
        code, out, _ = self.run_cli("--", PYTHON, "-c", "for i in range(10000): print(f'line {i}')")
        self.assertEqual(code, 0)
        self.assertLess(len(out.splitlines()), 60)
        self.assertIn("## Summary lines (0)", out)
        self.assertIn("## Last 15 lines", out)
        self.assertTrue(out.rstrip().endswith("line 9999"))

    def test_tail_sets_the_number_of_last_lines(self) -> None:
        _, out, _ = self.run_cli("--tail", "3", "--", PYTHON, "-c", "for i in range(10): print(i)")
        self.assertEqual(out.split("## Last 3 lines\n", 1)[1].splitlines(), ["7", "8", "9"])

    def test_exit_line_names_the_command(self) -> None:
        _, out, _ = self.run_cli("--", PYTHON, "-c", "print(1)")
        self.assertRegex(out.splitlines()[1], r"^exit 0 after \d+\.\ds: .+ -c 'print\(1\)'$")


class LabelTest(unittest.TestCase):
    def test_name_wins(self) -> None:
        self.assertEqual(run.label(["uv", "run", "pytest"], "Blender pick tests"), "blender-pick-tests")

    def test_first_two_words_without_env_assignments_and_paths(self) -> None:
        command = ["env", "BLENDER_USER_RESOURCES=/tmp/profile", "scripts/test-blender.sh", "-k", "pick"]
        self.assertEqual(run.label(command, None), "test-blender-sh-k")

    def test_plain_command(self) -> None:
        self.assertEqual(run.label(["uv", "run", "pytest", "-q"], None), "uv-run")

    def test_label_is_cut_to_40_characters(self) -> None:
        self.assertEqual(len(run.label(["x" * 80], None)), 40)


if __name__ == "__main__":
    unittest.main()
