import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_skills import cli
from agent_skills.render import COMMENT_LIMIT, cut
from agent_skills.tracker import is_decision
from fakes import FakeRunner, fixture_json, fixture_text, names_repo, with_origin

URCHIN_SPECS = [f"107-{name}.md" for name in "abilities capability-map hub inventory store title-slots ui-foundation victory window-shell".split()]
BLENDER_SPECS = ["12-contact-sheet-and-runbook.md", "12-sword-flourish-test.md", "35-draynor-region-import.md"]


class CutTest(unittest.TestCase):
    def test_short_text_is_kept(self) -> None:
        self.assertEqual(cut("abc", 3), "abc")

    def test_long_text_ends_with_the_count_of_cut_characters(self) -> None:
        self.assertEqual(cut("abcdef", 4), "abcd\n[cut: 2 more characters, run with --full]")

    def test_no_limit_keeps_everything(self) -> None:
        self.assertEqual(cut("abcdef", None), "abcdef")


class IsDecisionTest(unittest.TestCase):
    def test_a_first_line_that_starts_with_decisions(self) -> None:
        for body in ("### Decisions from the review of PR #97\n\n- a", "**Decisions**\n- a", "decisions: keep it", "Decisions from the review of #97, for the later tasks of #82:"):
            with self.subTest(body=body):
                self.assertTrue(is_decision(body))

    def test_other_first_lines(self) -> None:
        for body in ("The decisions below", "", "Decisionsmaking", "Refined this one.\nDecisions: none"):
            with self.subTest(body=body):
                self.assertFalse(is_decision(body))


class IssueVerbTest(unittest.TestCase):
    def setUp(self) -> None:
        self.checkout = tempfile.TemporaryDirectory()
        self.addCleanup(self.checkout.cleanup)
        (Path(self.checkout.name) / "spec" / "old").mkdir(parents=True)

    def run_issue(self, fixture: str, argv: list[str], specs: list[str], runner: FakeRunner | None = None) -> tuple[int, str, FakeRunner]:
        for name in specs:
            (Path(self.checkout.name) / "spec" / name).write_text("# spec\n")
        (Path(self.checkout.name) / "spec" / "old" / "game-animation.md").write_text("# old\n")
        runner = (runner or FakeRunner()).on("gh", "api", "graphql", stdout=fixture_json(fixture))
        runner.on("git", "rev-parse", "--show-toplevel", stdout=self.checkout.name + "\n")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(argv, runner)
        return code, out.getvalue(), runner

    def test_urchin_107_golden_output(self) -> None:
        code, out, _ = self.run_issue("issue-urchin-107.json", ["--repo", "julian-perge/urchin", "issue", "107"], URCHIN_SPECS)
        self.assertEqual(code, 0)
        self.assertEqual(out, fixture_text("issue-urchin-107.md"))

    def test_blender_35_golden_output(self) -> None:
        argv = ["--repo", "julian-perge/blender-addon-rs317-667mqo-makeup", "issue", "35"]
        code, out, _ = self.run_issue("issue-blender-35.json", argv, BLENDER_SPECS)
        self.assertEqual(code, 0)
        self.assertEqual(out, fixture_text("issue-blender-35.md"))

    def test_urchin_107_fits_in_5000_characters(self) -> None:
        _, out, _ = self.run_issue("issue-urchin-107.json", ["--repo", "julian-perge/urchin", "issue", "107"], URCHIN_SPECS)
        self.assertLessEqual(len(out), 5000)

    def test_counts_come_from_the_summary_not_the_rows_read(self) -> None:
        _, out, _ = self.run_issue("issue-urchin-107.json", ["--repo", "julian-perge/urchin", "issue", "107"], URCHIN_SPECS)
        self.assertIn("- Sub-issues: 29 open of 62\n", out)

    def test_the_table_shows_10_rows_open_first(self) -> None:
        _, out, _ = self.run_issue("issue-urchin-107.json", ["--repo", "julian-perge/urchin", "issue", "107"], URCHIN_SPECS)
        rows = [line for line in out.splitlines() if re.match(r"\| #\d", line)]
        self.assertEqual(len(rows), 10)
        self.assertTrue(all("| OPEN |" in row for row in rows))
        self.assertIn("[cut: 4 more rows, run with --full]", out)

    def test_full_prints_the_whole_body_every_comment_and_every_row(self) -> None:
        _, out, _ = self.run_issue("issue-urchin-107.json", ["--repo", "julian-perge/urchin", "issue", "107", "--full"], URCHIN_SPECS)
        self.assertNotIn("[cut:", out)
        self.assertEqual(len([line for line in out.splitlines() if re.match(r"\| #\d", line)]), 14)
        self.assertIn("## Not yet specified", out)

    def test_newest_three_comments_show_with_the_total(self) -> None:
        argv = ["--repo", "julian-perge/blender-addon-rs317-667mqo-makeup", "issue", "12"]
        _, out, _ = self.run_issue("issue-blender-12.json", argv, BLENDER_SPECS)
        self.assertIn("## Comments (3 of 6, newest last)", out)
        self.assertEqual(out.count("\n### @"), 3)

    def test_several_rule_3_files_are_listed_and_no_spec_is_named(self) -> None:
        argv = ["--repo", "julian-perge/blender-addon-rs317-667mqo-makeup", "issue", "12"]
        _, out, _ = self.run_issue("issue-blender-12.json", argv, BLENDER_SPECS)
        self.assertIn("- Spec: none (candidates: spec/12-contact-sheet-and-runbook.md, spec/12-sword-flourish-test.md)\n", out)

    def test_spec_from_the_issue_body_and_closed_blockers(self) -> None:
        argv = ["--repo", "julian-perge/blender-addon-rs317-667mqo-makeup", "issue", "51"]
        _, out, _ = self.run_issue("issue-blender-51.json", argv, BLENDER_SPECS)
        self.assertIn("- Spec: spec/35-draynor-region-import.md (from issue body)\n", out)
        self.assertIn("- Open blockers: none (closed: #50, #48)\n", out)
        self.assertIn("- Parent: #35 Import a map chunk (terrain and scenery) into Blender\n", out)

    def test_blender_84_golden_output_with_decisions_on_the_issue_and_its_parent(self) -> None:
        argv = ["--repo", "julian-perge/blender-addon-rs317-667mqo-makeup", "issue", "84"]
        code, out, _ = self.run_issue("issue-blender-84.json", argv, ["82-gltf-export-findings.md"])
        self.assertEqual(code, 0)
        self.assertEqual(out, fixture_text("issue-blender-84.md"))

    def test_decisions_print_whole_and_oldest_first_before_the_comments(self) -> None:
        argv = ["--repo", "julian-perge/blender-addon-rs317-667mqo-makeup", "issue", "84"]
        _, out, _ = self.run_issue("issue-blender-84.json", argv, ["82-gltf-export-findings.md"])
        self.assertIn("## Decisions (2)\n", out)
        self.assertLess(out.index("### #82 @"), out.index("### #84 @"))
        self.assertLess(out.index("## Body"), out.index("## Decisions"))
        self.assertLess(out.index("## Decisions"), out.index("## Comments"))
        self.assertNotIn("[cut: ", out.split("## Decisions", 1)[1].split("## Comments", 1)[0])

    def test_comments_leave_out_the_decisions_and_count_the_rest(self) -> None:
        data = json.loads(fixture_text("issue-blender-12.json"))
        data["data"]["repository"]["issue"]["comments"]["nodes"][-2]["body"] = "Decisions from the review of #20:\n\n- keep it"
        argv = ["--repo", "julian-perge/blender-addon-rs317-667mqo-makeup", "issue", "12"]
        _, out, _ = self.run_issue_data(data, argv, BLENDER_SPECS)
        self.assertIn("## Decisions (1)\n", out)
        self.assertIn("## Comments (3 of 5, newest last)", out)
        self.assertEqual(out.count("\n### @"), 3)
        self.assertNotIn("keep it", out.split("## Comments", 1)[1])

    def test_a_long_decision_is_not_cut_without_full(self) -> None:
        data = json.loads(fixture_text("issue-blender-12.json"))
        long_body = "### Decisions from the plan of #12\n\n" + "x" * 2 * COMMENT_LIMIT
        data["data"]["repository"]["issue"]["comments"]["nodes"][0]["body"] = long_body
        argv = ["--repo", "julian-perge/blender-addon-rs317-667mqo-makeup", "issue", "12"]
        _, out, _ = self.run_issue_data(data, argv, BLENDER_SPECS)
        self.assertIn(long_body + "\n", out)

    def test_an_issue_with_no_decision_has_no_decisions_section(self) -> None:
        _, out, _ = self.run_issue("issue-urchin-107.json", ["--repo", "julian-perge/urchin", "issue", "107"], URCHIN_SPECS)
        self.assertNotIn("## Decisions", out)

    def run_issue_data(self, data: dict, argv: list[str], specs: list[str]) -> tuple[int, str, FakeRunner]:
        runner = FakeRunner().on("gh", "api", "graphql", stdout=json.dumps(data))
        return self.run_issue("issue-blender-12.json", argv, specs, runner)

    def test_one_gh_call_that_names_the_origin_repo(self) -> None:
        _, _, runner = self.run_issue("issue-blender-51.json", ["issue", "51"], BLENDER_SPECS, with_origin(FakeRunner()))
        self.assertEqual(len(runner.gh_calls()), 1)
        self.assertTrue(names_repo(runner.gh_calls()[0], "julian-perge/agent-skills"))


if __name__ == "__main__":
    unittest.main()
