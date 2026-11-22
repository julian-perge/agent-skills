import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_skills import brief, cli, render
from fakes import FakeRunner, fixture_json, fixture_text

BLENDER = "julian-perge/blender-addon-rs317-667mqo-makeup"
BLENDER_SPECS = ["12-contact-sheet-and-runbook.md", "12-sword-flourish-test.md", "35-draynor-region-import.md"]

INTRO = None
EVERY = [INTRO, "Helpers"]

BLENDER_HEADINGS = {
    "idea": EVERY + ["Stages", "Design", "Commit review", "Reports and output decisions"],
    "design": EVERY + ["Stages", "Design", "Commit review", "Reports and output decisions"],
    "spec": EVERY + ["Design", "Spec", "Commit review", "Reports and output decisions"],
    "plan": EVERY + ["Labels", "Plan", "Commit review", "Reports and output decisions"],
    "build": EVERY + ["Build", "Commit review", "Reports and output decisions"],
    "bug": EVERY + ["Build", "Commit review", "Reports and output decisions"],
    "review": EVERY + ["Commit review", "Review", "Reports and output decisions"],
}

URCHIN_HEADINGS = {
    "idea": EVERY + ["Stages", "Design", "Reports"],
    "design": EVERY + ["Stages", "Design", "Reports"],
    "spec": EVERY + ["Design", "Spec", "Reports"],
    "plan": EVERY + ["Labels", "Plan", "Reports"],
    "build": EVERY + ["Build", "Reports"],
    "bug": EVERY + ["Build", "Reports"],
    "review": EVERY + ["Review", "Reports"],
}


def heading(section: str) -> str | None:
    first = section.splitlines()[0]
    return first.removeprefix("## ") if first.startswith("## ") else None


def file_sections(text: str) -> dict[str | None, str]:
    """Cuts the file at each line that starts with "## ", independently of brief.py."""
    starts = [0] + [i + 1 for i, char in enumerate(text) if char == "\n" and text.startswith("## ", i + 1)]
    pieces = [text[start:end] for start, end in zip(starts, starts[1:] + [len(text)])]
    return {heading(piece): piece for piece in pieces}


class StageSectionsTest(unittest.TestCase):
    def check_fixture(self, name: str, expected: dict[str, list[str | None]]) -> None:
        text = fixture_text(name)
        whole = file_sections(text)
        for stage, headings in expected.items():
            with self.subTest(fixture=name, stage=stage):
                got = brief.stage_sections(text, stage)
                self.assertEqual([heading(section) for section in got], headings)
                self.assertEqual(got[1:], [whole[title] for title in headings[1:]])

    def test_blender_stages(self) -> None:
        self.check_fixture("workflow-blender.md", BLENDER_HEADINGS)

    def test_urchin_stages(self) -> None:
        self.check_fixture("workflow-urchin.md", URCHIN_HEADINGS)

    def test_the_intro_drops_its_title_and_its_first_paragraph(self) -> None:
        for name in ("workflow-blender.md", "workflow-urchin.md"):
            with self.subTest(fixture=name):
                text = fixture_text(name)
                intro = brief.stage_sections(text, "build")[0]
                self.assertTrue(intro.startswith("The user types each stage."))
                self.assertTrue(text.endswith(intro + text[text.index("## Helpers\n"):]))

    def test_an_intro_of_one_paragraph_gives_no_section(self) -> None:
        self.assertEqual(brief.stage_sections("# Workflow\n\nRead this first.\n## Build\nb\n", "build"), ["## Build\nb\n"])

    def test_the_earlier_layout_section_goes_to_no_stage(self) -> None:
        text = "## Earlier layout\nold paths\n## Build\nb\n"
        for stage in brief.STAGES:
            with self.subTest(stage=stage):
                self.assertNotIn("## Earlier layout\nold paths\n", brief.stage_sections(text, stage))

    def test_an_unknown_heading_goes_to_every_stage(self) -> None:
        text = fixture_text("workflow-urchin.md") + "## Local notes\nKeep this.\n"
        for stage in brief.STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(brief.stage_sections(text, stage)[-1], "## Local notes\nKeep this.\n")

    def test_the_checks_and_the_evidence_paths_go_to_build_bug_and_review(self) -> None:
        text = "## Checks\n- `just gut`\n## Evidence paths\n- `scenes/**`\n"
        for stage in brief.STAGES:
            with self.subTest(stage=stage):
                wanted = ["## Checks\n- `just gut`\n", "## Evidence paths\n- `scenes/**`\n"] if stage in ("build", "bug", "review") else []
                self.assertEqual(brief.stage_sections(text, stage), wanted)

    def test_headings_match_by_first_word_without_case(self) -> None:
        text = "## BUILD steps\nb\n## review\nr\n"
        self.assertEqual(brief.stage_sections(text, "build"), ["## BUILD steps\nb\n"])

    def test_a_missing_known_heading_is_skipped(self) -> None:
        text = "## Helpers\nh\n## Review\nr\n"
        self.assertEqual(brief.stage_sections(text, "build"), ["## Helpers\nh\n"])

    def test_a_file_with_no_intro_gives_no_empty_section(self) -> None:
        self.assertEqual(brief.stage_sections("## Build\nb\n", "build"), ["## Build\nb\n"])

    def test_a_last_line_with_no_newline_is_kept(self) -> None:
        self.assertEqual(brief.stage_sections("# Workflow\n\nFirst.\n\nSecond.\n## Build\nb", "build"), ["Second.\n", "## Build\nb"])


class StageNameTest(unittest.TestCase):
    def test_command_names_give_the_same_sections(self) -> None:
        text = fixture_text("workflow-blender.md")
        for command, stage in (("idea-refine", "idea"), ("interview-me", "design"), ("test", "bug")):
            with self.subTest(command=command):
                self.assertEqual(brief.stage_name(command), stage)
                self.assertEqual(brief.stage_sections(text, command), brief.stage_sections(text, stage))

    def test_stage_names_are_their_own_name(self) -> None:
        for stage in brief.STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(brief.stage_name(stage), stage)

    def test_an_unknown_stage_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            brief.stage_name("ship")


class BriefVerbTest(unittest.TestCase):
    def setUp(self) -> None:
        checkout = tempfile.TemporaryDirectory()
        self.addCleanup(checkout.cleanup)
        self.root = Path(checkout.name)
        (self.root / "spec").mkdir()
        for name in BLENDER_SPECS:
            (self.root / "spec" / name).write_text("# spec\n")
        for name in ("AGENTS.md", "CLAUDE.md", "CODING_STANDARDS.md"):
            (self.root / name).write_text("# rules\n")
        (self.root / "docs" / "agents").mkdir(parents=True)
        self.workflow = fixture_text("workflow-blender.md")
        (self.root / "docs" / "agents" / "workflow.md").write_text(self.workflow)

    def run_cli(self, argv: list[str], *fixtures: str) -> tuple[int, str, str, FakeRunner]:
        runner = FakeRunner()
        for fixture in fixtures:
            stdout = fixture if fixture.startswith("{") else fixture_json(fixture)
            runner.on("gh", "api", "graphql", stdout=stdout)
        for _ in range(3):
            runner.on("git", "rev-parse", "--show-toplevel", stdout=str(self.root) + "\n")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--repo", BLENDER, *argv], runner)
        return code, out.getvalue(), err.getvalue(), runner

    def rules(self, stage: str) -> str:
        note = "These are all the rules of docs/agents/workflow.md that this stage needs. Do not read that file."
        return f"# Rules for {stage}, from docs/agents/workflow.md\n\n{note}\n\n" + "".join(brief.stage_sections(self.workflow, stage))

    def test_build_prints_the_rules_then_the_issue_from_its_second_line(self) -> None:
        code, out, _, _ = self.run_cli(["brief", "build", "35"], "issue-blender-35.json")
        _, issue, _, _ = self.run_cli(["issue", "35"], "issue-blender-35.json")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith(self.rules("build") + "# Issue #35\n"))
        header = issue.split("\n", 1)[1].split("## Body\n", 1)[0]
        self.assertIn("# Issue #35\n" + header + "## Body\n", out)

    def test_the_issue_part_prints_the_whole_body_and_one_comment(self) -> None:
        _, out, _, _ = self.run_cli(["brief", "build", "35"], "issue-blender-35.json")
        _, full, _, _ = self.run_cli(["issue", "35", "--full"], "issue-blender-35.json")
        body = full.split("## Body\n", 1)[1].split("## Comments", 1)[0]
        self.assertIn("## Body\n" + body + "## Comments", out)
        self.assertNotIn("[cut: ", body)
        self.assertIn("## Comments (1 of 3, newest last)", out)
        self.assertEqual(out.count("\n### @"), 1)

    def test_the_one_comment_is_not_cut(self) -> None:
        _, out, _, _ = self.run_cli(["brief", "build", "107"], "issue-urchin-107.json")
        _, full, _, _ = self.run_cli(["issue", "107", "--full"], "issue-urchin-107.json")
        newest = "\n### @" + full.rsplit("\n### @", 1)[1]
        self.assertGreater(len(newest), render.COMMENT_LIMIT)
        self.assertTrue(out.endswith(newest))
        self.assertNotIn("[cut: ", newest)

    def test_review_prints_the_rules_then_the_task_then_the_pr(self) -> None:
        code, out, _, _ = self.run_cli(["brief", "review", "66"], "pr-blender-66.json", "issue-blender-35.json")
        _, pr, _, _ = self.run_cli(["pr", "66"], "pr-blender-66.json")
        _, build, _, _ = self.run_cli(["brief", "build", "35"], "issue-blender-35.json")
        task = build.removeprefix(self.rules("build") + "# Issue #35\n")
        self.assertEqual(code, 0)
        self.assertEqual(out, self.rules("review") + "# Task #49\n" + task + "# PR #66\n" + pr.split("\n", 1)[1])

    def test_review_prints_the_decisions_of_the_task_before_the_pr(self) -> None:
        code, out, _, _ = self.run_cli(["brief", "review", "66"], "pr-blender-66.json", "issue-blender-84.json")
        self.assertEqual(code, 0)
        self.assertIn("## Decisions (2)\n", out)
        self.assertLess(out.index("## Decisions"), out.index("# PR #66\n"))

    def test_review_with_no_task_prints_only_the_pr(self) -> None:
        data = json.loads(fixture_json("pr-blender-66.json"))
        node = data["data"]["repository"]["pullRequest"]
        node["closingIssuesReferences"]["nodes"], node["body"], node["headRefName"] = [], "", "misc"
        code, out, _, runner = self.run_cli(["brief", "review", "66"], json.dumps(data))
        _, pr, _, _ = self.run_cli(["pr", "66"], json.dumps(data))
        self.assertEqual(code, 0)
        self.assertEqual(out, self.rules("review") + "# PR #66\n" + pr.split("\n", 1)[1])
        self.assertEqual(len(runner.gh_calls()), 1)

    def test_the_gh_calls_equal_those_of_issue(self) -> None:
        _, _, _, brief_runner = self.run_cli(["brief", "build", "35"], "issue-blender-35.json")
        _, _, _, issue_runner = self.run_cli(["issue", "35"], "issue-blender-35.json")
        self.assertEqual(brief_runner.gh_calls(), issue_runner.gh_calls())

    def test_review_adds_only_the_issue_call_of_the_task(self) -> None:
        _, _, _, brief_runner = self.run_cli(["brief", "review", "66"], "pr-blender-66.json", "issue-blender-35.json")
        _, _, _, pr_runner = self.run_cli(["pr", "66"], "pr-blender-66.json")
        _, _, _, issue_runner = self.run_cli(["issue", "49"], "issue-blender-35.json")
        self.assertEqual(brief_runner.gh_calls(), pr_runner.gh_calls() + issue_runner.gh_calls())

    def test_every_stage_but_review_uses_issue(self) -> None:
        for stage in ("idea", "design", "spec", "plan", "bug", "test"):
            with self.subTest(stage=stage):
                code, out, _, _ = self.run_cli(["brief", stage, "35"], "issue-blender-35.json")
                self.assertEqual(code, 0)
                self.assertIn("\n# Issue #35\n", out)

    def test_a_leading_hash_is_accepted(self) -> None:
        _, plain, _, _ = self.run_cli(["brief", "build", "35"], "issue-blender-35.json")
        code, hashed, _, _ = self.run_cli(["brief", "build", "#35"], "issue-blender-35.json")
        self.assertEqual(code, 0)
        self.assertEqual(hashed, plain)

    def test_full_is_passed_to_issue(self) -> None:
        _, out, _, _ = self.run_cli(["brief", "build", "35", "--full"], "issue-blender-35.json")
        _, issue, _, _ = self.run_cli(["issue", "35", "--full"], "issue-blender-35.json")
        self.assertTrue(out.endswith(issue.split("\n", 1)[1]))

    def test_a_command_name_prints_its_stage_name(self) -> None:
        _, out, _, _ = self.run_cli(["brief", "test"])
        self.assertEqual(out, self.rules("bug"))

    def test_no_number_prints_the_rules_only_and_calls_no_gh(self) -> None:
        code, out, _, runner = self.run_cli(["brief", "build"])
        self.assertEqual(code, 0)
        self.assertEqual(out, self.rules("build"))
        self.assertEqual(runner.gh_calls(), [])

    def test_no_workflow_file_gives_exit_2_and_names_setup_workflow(self) -> None:
        (self.root / "docs" / "agents" / "workflow.md").unlink()
        code, out, err, runner = self.run_cli(["brief", "build", "35"], "issue-blender-35.json")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("/agent-skills:setup-workflow", err)
        self.assertEqual(runner.gh_calls(), [])

    def test_an_unknown_stage_is_a_usage_error(self) -> None:
        code, out, _, _ = self.run_cli(["brief", "ship"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
