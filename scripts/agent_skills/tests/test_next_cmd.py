import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_skills import cli
from fakes import FakeRunner, fixture_json

BLENDER = "julian-perge/blender-addon-rs317-667mqo-makeup"
BLENDER_SPECS = ["12-contact-sheet-and-runbook.md", "12-sword-flourish-test.md", "35-draynor-region-import.md"]


class NextCmdTest(unittest.TestCase):
    def setUp(self) -> None:
        self.checkout = tempfile.TemporaryDirectory()
        self.addCleanup(self.checkout.cleanup)
        (Path(self.checkout.name) / "spec").mkdir()
        (Path(self.checkout.name) / "CODING_STANDARDS.md").write_text("# rules\n")

    def run_cmd(self, argv: list[str], fixtures: list[str], specs: list[str] = BLENDER_SPECS) -> tuple[int, str, str, FakeRunner]:
        for name in specs:
            (Path(self.checkout.name) / "spec" / name).write_text("# spec\n")
        runner = FakeRunner()
        for fixture in fixtures:
            runner.on("gh", "api", "graphql", stdout=fixture_json(fixture))
        runner.on("git", "rev-parse", "--show-toplevel", stdout=self.checkout.name + "\n")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv, runner)
        return code, out.getvalue(), err.getvalue(), runner

    def test_review_prints_the_review_line_of_the_pr(self) -> None:
        code, out, err, _ = self.run_cmd(["--repo", "julian-perge/urchin", "next-cmd", "review", "278"], ["pr-urchin-278.json"], ["107-ui-foundation.md"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "/agent-skills:review issue #273, PR #278, spec spec/107-ui-foundation.md, standard CODING_STANDARDS.md\n")
        self.assertEqual(err, "")

    def test_review_leaves_out_parts_and_names_them_on_stderr(self) -> None:
        code, out, err, _ = self.run_cmd(["--repo", BLENDER, "next-cmd", "review", "33"], ["pr-blender-33.json"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "/agent-skills:review PR #33, standard CODING_STANDARDS.md\n")
        self.assertEqual(err, "Left out of the review line: issue (no task found), spec (no task found).\n")

    def test_review_marks_a_branch_name_task_as_a_guess_on_stderr(self) -> None:
        code, out, err, _ = self.run_cmd(["--repo", BLENDER, "next-cmd", "review", "27"], ["pr-blender-27.json", "task-blender-22.json"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "/agent-skills:review issue #22, PR #27, spec spec/12-contact-sheet-and-runbook.md, standard CODING_STANDARDS.md\n")
        self.assertEqual(err, "Task #22 is from the branch name (guess).\n")

    def test_build_prints_the_frontier(self) -> None:
        code, out, _, runner = self.run_cmd(["--repo", "julian-perge/urchin", "next-cmd", "build", "107"], ["frontier-urchin-107.json"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "/agent-skills:build #204\n")
        self.assertEqual(len(runner.gh_calls()), 1)

    def test_build_whole_prints_the_parent(self) -> None:
        code, out, _, _ = self.run_cmd(["--repo", "julian-perge/urchin", "next-cmd", "build", "107", "--whole"], ["frontier-urchin-107.json"])
        self.assertEqual((code, out), (0, "/agent-skills:build #107\n"))

    def test_build_whole_with_no_frontier_exits_1(self) -> None:
        code, out, _, _ = self.run_cmd(["--repo", "julian-perge/urchin", "next-cmd", "build", "107", "--whole"], ["frontier-urchin-107-all-blocked.json"])
        self.assertEqual((code, out), (1, ""))

    def test_build_with_no_ready_for_agent_sub_issue_exits_1(self) -> None:
        code, _, err, _ = self.run_cmd(["--repo", BLENDER, "next-cmd", "build", "35"], ["frontier-blender-35.json"])
        self.assertEqual(code, 1)
        self.assertEqual(err, "No frontier for #35: no open sub-issue is ready-for-agent, unblocked and unassigned: 1 without ready-for-agent.\n")

    def test_build_with_no_frontier_exits_1(self) -> None:
        code, out, err, _ = self.run_cmd(["--repo", "julian-perge/urchin", "next-cmd", "build", "107"], ["frontier-urchin-107-all-blocked.json"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err, "No frontier for #107: no open sub-issue is ready-for-agent, unblocked and unassigned: 2 blocked, 1 assigned.\n")

    def test_plan_prints_the_spec(self) -> None:
        code, out, err, _ = self.run_cmd(["--repo", BLENDER, "next-cmd", "plan", "22"], ["task-blender-22.json"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "/agent-skills:plan #22, spec spec/12-contact-sheet-and-runbook.md\n")
        self.assertEqual(err, "")

    def test_plan_marks_a_file_name_spec_as_a_guess_on_stderr(self) -> None:
        code, out, err, _ = self.run_cmd(["--repo", BLENDER, "next-cmd", "plan", "35"], ["task-blender-35.json"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "/agent-skills:plan #35, spec spec/35-draynor-region-import.md\n")
        self.assertEqual(err, "Spec spec/35-draynor-region-import.md is from the file name (guess).\n")

    def test_plan_with_no_spec_exits_1(self) -> None:
        code, out, err, _ = self.run_cmd(["--repo", BLENDER, "next-cmd", "plan", "31"], ["task-blender-31.json"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err, "#31 has no spec.\n")

    def test_plan_with_several_candidates_exits_1_and_lists_them(self) -> None:
        code, _, err, _ = self.run_cmd(["--repo", BLENDER, "next-cmd", "plan", "12"], ["issue-blender-12.json"])
        self.assertEqual(code, 1)
        self.assertEqual(err, "#12 has no spec. Candidates: spec/12-contact-sheet-and-runbook.md, spec/12-sword-flourish-test.md.\n")

    def test_spec_prints_the_spec_command_with_no_gh_call(self) -> None:
        code, out, _, runner = self.run_cmd(["next-cmd", "spec", "#69"], [])
        self.assertEqual(code, 0)
        self.assertEqual(out, "/agent-skills:spec #69\n")
        self.assertEqual(runner.calls, [])

    def test_an_unknown_stage_is_a_usage_error(self) -> None:
        code, _, _, _ = self.run_cmd(["next-cmd", "ship", "5"], [])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
