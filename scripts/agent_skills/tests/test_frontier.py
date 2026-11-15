import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from agent_skills import cli
from agent_skills.tracker import SubIssue, frontier
from fakes import FakeRunner, fixture_json, fixture_text, names_repo, with_origin


def sub(
    number: int,
    state: str = "OPEN",
    assignees: tuple[str, ...] = (),
    open_blockers: int = 0,
    labels: tuple[str, ...] = ("ready-for-agent",),
) -> SubIssue:
    return SubIssue(number, f"Task {number}", state, assignees, open_blockers, labels)


class FrontierRuleTest(unittest.TestCase):
    def test_lowest_open_unblocked_unassigned_number_wins(self) -> None:
        subs = [sub(12), sub(9, open_blockers=1), sub(10, assignees=("julian-perge",)), sub(8, state="CLOSED"), sub(11)]
        self.assertEqual(frontier(subs).number, 11)

    def test_a_sub_issue_without_ready_for_agent_is_skipped(self) -> None:
        subs = [sub(5, labels=("ready-for-human",)), sub(6, labels=("enhancement", "ready-for-agent"))]
        self.assertEqual(frontier(subs).number, 6)

    def test_order_of_the_sub_issues_does_not_matter(self) -> None:
        self.assertEqual(frontier([sub(30), sub(21), sub(25)]).number, 21)

    def test_blocked_and_assigned_tasks_give_no_frontier(self) -> None:
        result = frontier([sub(5, open_blockers=2), sub(6, assignees=("someone",)), sub(7, state="CLOSED")])
        self.assertIsNone(result.number)
        self.assertEqual(result.reason, "no open sub-issue is ready-for-agent, unblocked and unassigned: 1 blocked, 1 assigned")

    def test_sub_issues_without_ready_for_agent_give_no_frontier(self) -> None:
        result = frontier([sub(51, labels=("ready-for-human",)), sub(67, labels=("needs-triage",)), sub(68, open_blockers=1)])
        self.assertIsNone(result.number)
        self.assertEqual(result.reason, "no open sub-issue is ready-for-agent, unblocked and unassigned: 2 without ready-for-agent, 1 blocked")

    def test_all_closed_gives_no_frontier(self) -> None:
        result = frontier([sub(5, state="CLOSED"), sub(6, state="CLOSED")])
        self.assertIsNone(result.number)
        self.assertEqual(result.reason, "all 2 sub-issues are closed")

    def test_no_sub_issues_gives_no_frontier(self) -> None:
        result = frontier([])
        self.assertIsNone(result.number)
        self.assertEqual(result.reason, "no sub-issues")


class FrontierVerbTest(unittest.TestCase):
    def run_frontier(self, fixture: str, number: str, repo: str = "julian-perge/urchin") -> tuple[int, str, FakeRunner]:
        runner = FakeRunner().on("gh", "api", "graphql", stdout=fixture_json(fixture))
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["--repo", repo, "frontier", number], runner)
        return code, out.getvalue(), runner

    def test_urchin_golden_output(self) -> None:
        code, out, _ = self.run_frontier("frontier-urchin-107.json", "107")
        self.assertEqual(code, 0)
        self.assertEqual(out, fixture_text("frontier-urchin-107.md"))

    def test_blender_golden_output(self) -> None:
        code, out, _ = self.run_frontier("frontier-blender-35.json", "35", "julian-perge/blender-addon-rs317-667mqo-makeup")
        self.assertEqual(code, 0)
        self.assertEqual(out, fixture_text("frontier-blender-35.md"))

    def test_every_open_sub_issue_blocked_or_assigned_exits_0(self) -> None:
        code, out, _ = self.run_frontier("frontier-urchin-107-all-blocked.json", "107")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[-1], "Frontier: none (no open sub-issue is ready-for-agent, unblocked and unassigned: 2 blocked, 1 assigned)")

    def test_all_closed_exits_0(self) -> None:
        code, out, _ = self.run_frontier("frontier-blender-35-all-closed.json", "35")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[-1], "Frontier: none (all 3 sub-issues are closed)")

    def test_no_sub_issues_exits_0(self) -> None:
        code, out, _ = self.run_frontier("frontier-urchin-204-none.json", "204")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[-1], "Frontier: none (no sub-issues)")

    def test_a_leading_hash_is_accepted(self) -> None:
        code, _, runner = self.run_frontier("frontier-urchin-107.json", "#107")
        self.assertEqual(code, 0)
        self.assertIn("number=107", runner.gh_calls()[0])

    def test_one_gh_call_that_names_the_origin_repo(self) -> None:
        runner = with_origin(FakeRunner()).on("gh", "api", "graphql", stdout=fixture_json("frontier-urchin-107.json"))
        with redirect_stdout(io.StringIO()):
            cli.main(["frontier", "107"], runner)
        self.assertEqual(len(runner.gh_calls()), 1)
        self.assertTrue(all(names_repo(call, "julian-perge/agent-skills") for call in runner.gh_calls()))

    def test_missing_gh_exits_2(self) -> None:
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = cli.main(["--repo", "julian-perge/urchin", "frontier", "107"], FakeRunner(missing=frozenset({"gh"})))
        self.assertEqual(code, 2)
        self.assertIn("`gh` is not on PATH", err.getvalue())

    def test_outside_a_repo_exits_2(self) -> None:
        runner = FakeRunner().on("git", "remote", "get-url", "origin", returncode=128, stderr="fatal: not a git repository\n")
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = cli.main(["frontier", "107"], runner)
        self.assertEqual(code, 2)
        self.assertEqual(runner.gh_calls(), [])

    def test_a_non_number_is_a_usage_error(self) -> None:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["frontier", "abc"], FakeRunner()), 2)


if __name__ == "__main__":
    unittest.main()
