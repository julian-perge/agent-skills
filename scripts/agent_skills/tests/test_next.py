import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_skills import cli
from fakes import FakeRunner, fixture_json, fixture_text, names_repo

BLENDER = "julian-perge/blender-addon-rs317-667mqo-makeup"
GITHUB_WORKFLOW = "## Workflow\n\n- Tasks are tracked in GitHub Issues for julian-perge/blender-addon-rs317-667mqo-makeup, with the `gh` CLI.\n\n## Other\n"
FILES_WORKFLOW = "## Workflow\n\n- Tasks are tracked in `tasks/todo.md`, and `tasks/` is committed.\n"


class NextVerbTest(unittest.TestCase):
    def setUp(self) -> None:
        self.checkout = tempfile.TemporaryDirectory()
        self.addCleanup(self.checkout.cleanup)
        root = Path(self.checkout.name)
        (root / "docs" / "agents").mkdir(parents=True)
        (root / "docs" / "agents" / "workflow.md").write_text("# Workflow\n")
        (root / "spec" / "old").mkdir(parents=True)
        for name in ("12-contact-sheet-and-runbook.md", "12-sword-flourish-test.md", "35-draynor-region-import.md", "old/game-animation.md"):
            (root / "spec" / name).write_text("# spec\n")
        (root / "AGENTS.md").write_text("# Agents\n\n" + GITHUB_WORKFLOW)
        (root / "CLAUDE.md").write_text("@AGENTS.md\n")
        (root / "CODING_STANDARDS.md").write_text("# Standards\n")

    def run_next(self, pages: list[str], bodies: list[str] = ("next-blender-sub-bodies-35.json",)) -> tuple[int, str, str, FakeRunner]:  # type: ignore[assignment]
        runner = FakeRunner().on("git", "rev-parse", "--show-toplevel", stdout=self.checkout.name + "\n")
        for page in pages:
            runner.on("gh", "api", "graphql", "-f", stdout=page)
        for body in bodies:
            runner.on("gh", "api", "graphql", "number=35", stdout=fixture_json(body))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--repo", BLENDER, "next"], runner)
        return code, out.getvalue(), err.getvalue(), runner

    def test_blender_golden_output(self) -> None:
        code, out, _, _ = self.run_next([fixture_json("next-blender-page-1.json")])
        self.assertEqual(code, 0)
        self.assertEqual(out, fixture_text("next-blender.md"))

    def test_the_same_tracker_state_gives_the_same_output(self) -> None:
        first = self.run_next([fixture_json("next-blender-page-1.json")])[1]
        second = self.run_next([fixture_json("next-blender-page-1.json")])[1]
        self.assertEqual(first, second)

    def test_one_call_per_page_plus_one_per_plan_candidate(self) -> None:
        _, _, _, runner = self.run_next([fixture_json("next-blender-page-1.json")])
        self.assertEqual(len(runner.gh_calls()), 2)
        self.assertIn("number=35", runner.gh_calls()[1])
        self.assertTrue(all(names_repo(call, BLENDER) for call in runner.gh_calls()))

    def test_later_pages_follow_the_cursor_and_skip_the_pull_requests(self) -> None:
        data = json.loads(fixture_json("next-blender-page-1.json"))
        nodes = data["data"]["repository"]["issues"]["nodes"]
        first = {"data": {"repository": {"issues": {"pageInfo": {"hasNextPage": True, "endCursor": "CURSOR1"}, "nodes": nodes[:6]}, "pullRequests": {"nodes": []}}}}
        second = {"data": {"repository": {"issues": {"pageInfo": {"hasNextPage": False, "endCursor": "CURSOR2"}, "nodes": nodes[6:]}}}}
        code, out, _, runner = self.run_next([json.dumps(first), json.dumps(second)])
        self.assertEqual(code, 0)
        self.assertEqual(out, fixture_text("next-blender.md"))
        calls = runner.gh_calls()
        self.assertEqual(len(calls), 3)
        self.assertIn("pulls=true", calls[0])
        self.assertFalse(any(arg.startswith("after=") for arg in calls[0]))
        self.assertIn("after=CURSOR1", calls[1])
        self.assertIn("pulls=false", calls[1])

    def test_no_workflow_doc_exits_2_before_any_gh_call(self) -> None:
        (Path(self.checkout.name) / "docs" / "agents" / "workflow.md").unlink()
        code, out, err, runner = self.run_next([])
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err, "No docs/agents/workflow.md in this repo. Run /agent-skills:setup-workflow first.\n")
        self.assertEqual(runner.gh_calls(), [])

    def test_files_mode_exits_2_before_any_gh_call(self) -> None:
        (Path(self.checkout.name) / "AGENTS.md").write_text("# Agents\n\n" + FILES_WORKFLOW)
        code, _, err, runner = self.run_next([])
        self.assertEqual(code, 2)
        self.assertEqual(err, "The ## Workflow block of AGENTS.md does not say that tasks are tracked in GitHub Issues. `next` does not support files mode.\n")
        self.assertEqual(runner.gh_calls(), [])

    def test_the_workflow_block_can_be_in_claude_md(self) -> None:
        (Path(self.checkout.name) / "AGENTS.md").unlink()
        (Path(self.checkout.name) / "CLAUDE.md").write_text("# Claude\n\n" + GITHUB_WORKFLOW)
        self.assertEqual(self.run_next([fixture_json("next-blender-page-1.json")])[0], 0)


if __name__ == "__main__":
    unittest.main()
