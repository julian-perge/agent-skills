import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_skills import cli
from agent_skills.render import review_line
from agent_skills.tracker import SpecMatch, TaskMatch, pr_task, standard_file
from fakes import FakeRunner, fixture_json, fixture_text, names_repo, with_origin

URCHIN_SPECS = ["107-ui-foundation.md", "107-window-shell.md"]
BLENDER_SPECS = ["35-draynor-region-import.md"]


class PrTaskTest(unittest.TestCase):
    def test_closing_reference_comes_first(self) -> None:
        self.assertEqual(pr_task((273, 274), "Closes #12", "fix/9-gaps"), TaskMatch(273, "closing reference"))

    def test_closes_line_in_the_body(self) -> None:
        self.assertEqual(pr_task((), "Some text.\n\nCloses #43", "feat/9-x"), TaskMatch(43, "body"))

    def test_other_closing_keywords_count(self) -> None:
        self.assertEqual(pr_task((), "fixes #274", "docs/worker-trial"), TaskMatch(274, "body"))

    def test_branch_number_is_a_guess(self) -> None:
        self.assertEqual(pr_task((), "Follow-up to the runbook.", "docs/22-runbook-acceptance-fixes"), TaskMatch(22, "branch name", guess=True))

    def test_a_number_later_in_the_branch_name_does_not_count(self) -> None:
        self.assertEqual(pr_task((), "", "claude/agent-skills-spec-107-c525e4"), TaskMatch(None, "none"))

    def test_no_task(self) -> None:
        self.assertEqual(pr_task((), "Mentions #12 but closes nothing.", "docs/review-followups"), TaskMatch(None, "none"))


class StandardFileTest(unittest.TestCase):
    def test_order_is_coding_standards_then_agents_then_claude(self) -> None:
        self.assertEqual(standard_file(frozenset({"AGENTS.md", "CLAUDE.md", "CODING_STANDARDS.md"})), "CODING_STANDARDS.md")
        self.assertEqual(standard_file(frozenset({"AGENTS.md", "CLAUDE.md"})), "AGENTS.md")
        self.assertEqual(standard_file(frozenset({"CLAUDE.md"})), "CLAUDE.md")
        self.assertIsNone(standard_file(frozenset()))


class ReviewLineTest(unittest.TestCase):
    def test_every_part(self) -> None:
        line = review_line(60, TaskMatch(43, "closing reference"), SpecMatch("spec/35-x.md", "issue body", False), "CODING_STANDARDS.md")
        self.assertEqual(line, "/agent-skills:review issue #43, PR #60, spec spec/35-x.md, standard CODING_STANDARDS.md")

    def test_parts_with_no_value_are_left_out(self) -> None:
        line = review_line(33, TaskMatch(None, "none"), SpecMatch(None, "none", False), None)
        self.assertEqual(line, "/agent-skills:review PR #33")


class PrVerbTest(unittest.TestCase):
    def setUp(self) -> None:
        self.checkout = tempfile.TemporaryDirectory()
        self.addCleanup(self.checkout.cleanup)
        (Path(self.checkout.name) / "spec").mkdir()
        for name in ("AGENTS.md", "CLAUDE.md", "CODING_STANDARDS.md"):
            (Path(self.checkout.name) / name).write_text("# rules\n")

    def run_pr(self, fixture: str, argv: list[str], specs: list[str], runner: FakeRunner | None = None) -> tuple[int, str, FakeRunner]:
        for name in specs:
            (Path(self.checkout.name) / "spec" / name).write_text("# spec\n")
        runner = (runner or FakeRunner()).on("gh", "api", "graphql", stdout=fixture_json(fixture))
        runner.on("git", "rev-parse", "--show-toplevel", stdout=self.checkout.name + "\n")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(argv, runner)
        return code, out.getvalue(), runner

    def test_urchin_278_golden_output(self) -> None:
        code, out, _ = self.run_pr("pr-urchin-278.json", ["--repo", "julian-perge/urchin", "pr", "278"], URCHIN_SPECS)
        self.assertEqual(code, 0)
        self.assertEqual(out, fixture_text("pr-urchin-278.md"))

    def test_blender_66_golden_output(self) -> None:
        argv = ["--repo", "julian-perge/blender-addon-rs317-667mqo-makeup", "pr", "66"]
        code, out, _ = self.run_pr("pr-blender-66.json", argv, BLENDER_SPECS)
        self.assertEqual(code, 0)
        self.assertEqual(out, fixture_text("pr-blender-66.md"))

    def test_the_last_two_lines_are_checkout_and_review(self) -> None:
        _, out, _ = self.run_pr("pr-urchin-278.json", ["--repo", "julian-perge/urchin", "pr", "278"], URCHIN_SPECS)
        self.assertEqual(
            out.splitlines()[-2:],
            [
                "Check out: gh pr checkout 278",
                "Review: /agent-skills:review issue #273, PR #278, spec spec/107-ui-foundation.md, standard CODING_STANDARDS.md",
            ],
        )

    def test_no_task_leaves_issue_and_spec_out_of_the_review_line(self) -> None:
        argv = ["--repo", "julian-perge/blender-addon-rs317-667mqo-makeup", "pr", "33"]
        _, out, runner = self.run_pr("pr-blender-33.json", argv, BLENDER_SPECS)
        self.assertIn("- Task: none\n", out)
        self.assertEqual(out.splitlines()[-1], "Review: /agent-skills:review PR #33, standard CODING_STANDARDS.md")
        self.assertEqual(len(runner.gh_calls()), 1)

    def test_a_long_body_is_cut(self) -> None:
        data = json.loads(fixture_json("pr-blender-66.json"))
        data["data"]["repository"]["pullRequest"]["body"] = "x" * 2500
        runner = FakeRunner().on("gh", "api", "graphql", stdout=json.dumps(data))
        runner.on("git", "rev-parse", "--show-toplevel", stdout=self.checkout.name + "\n")
        out = io.StringIO()
        with redirect_stdout(out):
            cli.main(["--repo", "julian-perge/blender-addon-rs317-667mqo-makeup", "pr", "66"], runner)
        self.assertIn("[cut: 500 more characters, run with --full]", out.getvalue())

    def test_one_gh_call_that_names_the_origin_repo_for_a_closing_reference(self) -> None:
        _, _, runner = self.run_pr("pr-urchin-278.json", ["pr", "278"], URCHIN_SPECS, with_origin(FakeRunner()))
        self.assertEqual(len(runner.gh_calls()), 1)
        self.assertTrue(names_repo(runner.gh_calls()[0], "julian-perge/agent-skills"))

    def test_a_branch_name_task_reads_the_task_in_a_second_call(self) -> None:
        argv = ["pr", "27"]
        runner = with_origin(FakeRunner()).on("gh", "api", "graphql", "number=27", stdout=fixture_json("pr-blender-27.json"))
        runner.on("gh", "api", "graphql", "number=22", stdout=fixture_json("task-blender-22.json"))
        _, out, runner = self.run_pr_with(runner, argv, ["12-contact-sheet-and-runbook.md", "12-sword-flourish-test.md"])
        self.assertIn("- Task: #22 The acceptance run of the hand-made motion runbook (from branch name) (guess)\n", out)
        self.assertIn("- Spec: spec/12-contact-sheet-and-runbook.md (from issue body)\n", out)
        self.assertEqual(len(runner.gh_calls()), 2)
        self.assertTrue(all(names_repo(call, "julian-perge/agent-skills") for call in runner.gh_calls()))

    def test_a_closes_line_task_reads_the_task_in_a_second_call(self) -> None:
        data = json.loads(fixture_json("pr-urchin-278.json"))
        data["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"] = []
        runner = FakeRunner().on("gh", "api", "graphql", "number=278", stdout=json.dumps(data))
        runner.on("gh", "api", "graphql", "number=273", stdout=fixture_json("task-urchin-273.json"))
        _, out, runner = self.run_pr_with(runner, ["--repo", "julian-perge/urchin", "pr", "278"], URCHIN_SPECS)
        self.assertIn("- Task: #273 Fix the comments, docs and small test gaps from the #107 re-reviews (from body)\n", out)
        self.assertIn("- Spec: spec/107-ui-foundation.md (from issue body)\n", out)
        self.assertEqual(len(runner.gh_calls()), 2)

    def run_pr_with(self, runner: FakeRunner, argv: list[str], specs: list[str]) -> tuple[int, str, FakeRunner]:
        for name in specs:
            (Path(self.checkout.name) / "spec" / name).write_text("# spec\n")
        runner.on("git", "rev-parse", "--show-toplevel", stdout=self.checkout.name + "\n")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(argv, runner)
        return code, out.getvalue(), runner


if __name__ == "__main__":
    unittest.main()
