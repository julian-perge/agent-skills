import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from agent_skills import cli
from agent_skills.tracker import is_decision
from fakes import FakeRunner, names_repo

URCHIN = "julian-perge/urchin"
URL = "https://github.com/julian-perge/urchin/issues/215#issuecomment-1"


class DecideVerbTest(unittest.TestCase):
    def run_cli(self, argv: list[str], stdin: str) -> tuple[int, str, str, FakeRunner]:
        runner = FakeRunner().on("gh", "issue", "comment", stdout=URL + "\n")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--repo", URCHIN, *argv], runner)
        return code, out.getvalue(), err.getvalue(), runner

    def posted(self, runner: FakeRunner) -> str:
        call = runner.gh_calls()[0]
        return call[call.index("--body") + 1]

    def test_review_with_a_pr_names_the_pr_in_the_first_line(self) -> None:
        code, out, _, runner = self.run_cli(["decide", "215", "--from", "review", "--pr", "287"], "- Start!, not PLAY.\n")
        self.assertEqual(code, 0)
        self.assertEqual(self.posted(runner), "### Decisions from the review of PR #287\n\n- Start!, not PLAY.")
        self.assertEqual(out, URL + "\n")

    def test_a_body_that_starts_with_the_same_header_posts_it_once(self) -> None:
        stdin = "### Decisions from the review of PR #287\n\n- Start!, not PLAY.\n"
        _, _, _, runner = self.run_cli(["decide", "215", "--from", "review", "--pr", "287"], stdin)
        self.assertEqual(self.posted(runner), "### Decisions from the review of PR #287\n\n- Start!, not PLAY.")

    def test_without_a_pr_the_first_line_names_the_issue(self) -> None:
        _, _, _, runner = self.run_cli(["decide", "82", "--from", "plan"], "- the outfit\n")
        self.assertTrue(self.posted(runner).startswith("### Decisions from the plan of #82\n\n"))

    def test_a_command_name_gives_its_stage_name(self) -> None:
        _, _, _, runner = self.run_cli(["decide", "13", "--from", "interview-me"], "- a\n")
        self.assertTrue(self.posted(runner).startswith("### Decisions from the design of #13\n"))

    def test_the_posted_comment_is_a_decision_comment(self) -> None:
        _, _, _, runner = self.run_cli(["decide", "215", "--from", "build"], "- a\n")
        self.assertTrue(is_decision(self.posted(runner)))

    def test_one_call_that_names_the_repo(self) -> None:
        _, _, _, runner = self.run_cli(["decide", "215", "--from", "build"], "- a\n")
        self.assertEqual(len(runner.gh_calls()), 1)
        self.assertEqual(runner.gh_calls()[0][:4], ["gh", "issue", "comment", "215"])
        self.assertTrue(names_repo(runner.gh_calls()[0], URCHIN))

    def test_an_empty_body_exits_1_and_posts_nothing(self) -> None:
        code, _, err, runner = self.run_cli(["decide", "215", "--from", "build"], " \n\n")
        self.assertEqual(code, 1)
        self.assertIn("stdin", err)
        self.assertEqual(runner.calls, [])

    def test_an_unknown_stage_is_a_usage_error(self) -> None:
        code, _, _, runner = self.run_cli(["decide", "215", "--from", "ship"], "- a\n")
        self.assertEqual(code, 2)
        self.assertEqual(runner.calls, [])


if __name__ == "__main__":
    unittest.main()
