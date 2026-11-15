import unittest

from agent_skills.tracker import Issue, SpecMatch, first_spec_path, spec_for

SPECS = frozenset({"spec/35-draynor-region-import.md", "spec/12-contact-sheet-and-runbook.md", "spec/12-sword-flourish-test.md", "spec/notes.md"})


class FirstSpecPathTest(unittest.TestCase):
    def test_spec_line_with_backticks(self) -> None:
        body = "Part of the import.\n\nSpec: `spec/107-ui-foundation.md` (Part 1, cutscene clips)\n"
        self.assertEqual(first_spec_path(body), "spec/107-ui-foundation.md")

    def test_bold_spec_line_wins_over_an_earlier_path(self) -> None:
        body = "Worked example: spec/old/battle.md\n**Spec:** spec/35-draynor-region-import.md\n"
        self.assertEqual(first_spec_path(body), "spec/35-draynor-region-import.md")

    def test_path_anywhere_when_there_is_no_spec_line(self) -> None:
        self.assertEqual(first_spec_path("See https://github.com/o/r/blob/main/spec/35-draynor-region-import.md."), "spec/35-draynor-region-import.md")

    def test_no_path(self) -> None:
        self.assertIsNone(first_spec_path("No spec yet."))


class SpecForTest(unittest.TestCase):
    def test_rule_1_issue_body(self) -> None:
        issue = Issue(51, "Compare the render", body="Spec: `spec/35-draynor-region-import.md`", parent_number=35)
        self.assertEqual(spec_for(issue, SPECS), SpecMatch("spec/35-draynor-region-import.md", "issue body", guess=False))

    def test_rule_2_parent_body(self) -> None:
        issue = Issue(51, "Compare the render", body="No path here.", parent_number=35, parent_body="Spec: spec/35-draynor-region-import.md")
        self.assertEqual(spec_for(issue, SPECS), SpecMatch("spec/35-draynor-region-import.md", "parent body", guess=False))

    def test_a_path_that_does_not_exist_falls_through_to_the_next_rule(self) -> None:
        issue = Issue(51, "Compare the render", body="Spec: spec/old/game-animation.md", parent_number=35, parent_body="spec/35-draynor-region-import.md")
        self.assertEqual(spec_for(issue, SPECS).source, "parent body")

    def test_rule_3_one_file_for_the_issue_is_a_guess(self) -> None:
        self.assertEqual(spec_for(Issue(35, "Import a map chunk"), SPECS), SpecMatch("spec/35-draynor-region-import.md", "file name", guess=True))

    def test_rule_3_one_file_for_the_parent_is_a_guess(self) -> None:
        self.assertEqual(spec_for(Issue(36, "Placements", parent_number=35), SPECS).path, "spec/35-draynor-region-import.md")

    def test_rule_3_several_files_names_no_spec_and_lists_them(self) -> None:
        self.assertEqual(
            spec_for(Issue(12, "Animations", body="Old spec: spec/old/game-animation.md"), SPECS),
            SpecMatch(None, "none", guess=False, candidates=("spec/12-contact-sheet-and-runbook.md", "spec/12-sword-flourish-test.md")),
        )

    def test_no_spec(self) -> None:
        self.assertEqual(spec_for(Issue(31, "Decode errors"), SPECS), SpecMatch(None, "none", guess=False))

    def test_unnumbered_spec_files_never_match_rule_3(self) -> None:
        self.assertIsNone(spec_for(Issue(31, "Decode errors"), frozenset({"spec/notes.md"})).path)


if __name__ == "__main__":
    unittest.main()
