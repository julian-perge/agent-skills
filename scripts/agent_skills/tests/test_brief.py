import unittest

from agent_skills import brief
from fakes import fixture_text

INTRO = None
EVERY = [INTRO, "Helpers"]

BLENDER_HEADINGS = {
    "idea": EVERY + ["Stages", "Design", "Commit review", "Earlier layout", "Reports and output decisions"],
    "design": EVERY + ["Stages", "Design", "Commit review", "Earlier layout", "Reports and output decisions"],
    "spec": EVERY + ["Design", "Spec", "Commit review", "Earlier layout", "Reports and output decisions"],
    "plan": EVERY + ["Labels", "Plan", "Commit review", "Earlier layout", "Reports and output decisions"],
    "build": EVERY + ["Build", "Commit review", "Earlier layout", "Reports and output decisions"],
    "bug": EVERY + ["Build", "Commit review", "Earlier layout", "Reports and output decisions"],
    "review": EVERY + ["Commit review", "Review", "Earlier layout", "Reports and output decisions"],
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
                self.assertEqual(got, [whole[title] for title in headings])

    def test_blender_stages(self) -> None:
        self.check_fixture("workflow-blender.md", BLENDER_HEADINGS)

    def test_urchin_stages(self) -> None:
        self.check_fixture("workflow-urchin.md", URCHIN_HEADINGS)

    def test_the_intro_is_the_text_before_the_first_heading(self) -> None:
        text = fixture_text("workflow-blender.md")
        intro = brief.stage_sections(text, "build")[0]
        self.assertTrue(text.startswith(intro))
        self.assertTrue(text[len(intro):].startswith("## Helpers\n"))

    def test_an_unknown_heading_goes_to_every_stage(self) -> None:
        text = fixture_text("workflow-urchin.md") + "## Local notes\nKeep this.\n"
        for stage in brief.STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(brief.stage_sections(text, stage)[-1], "## Local notes\nKeep this.\n")

    def test_headings_match_by_first_word_without_case(self) -> None:
        text = "Intro\n## BUILD steps\nb\n## review\nr\n"
        self.assertEqual(brief.stage_sections(text, "build"), ["Intro\n", "## BUILD steps\nb\n"])

    def test_a_missing_known_heading_is_skipped(self) -> None:
        text = "Intro\n## Helpers\nh\n## Review\nr\n"
        self.assertEqual(brief.stage_sections(text, "build"), ["Intro\n", "## Helpers\nh\n"])

    def test_a_file_with_no_intro_gives_no_empty_section(self) -> None:
        self.assertEqual(brief.stage_sections("## Build\nb\n", "build"), ["## Build\nb\n"])

    def test_a_last_line_with_no_newline_is_kept(self) -> None:
        self.assertEqual(brief.stage_sections("Intro\n## Build\nb", "build"), ["Intro\n", "## Build\nb"])


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


if __name__ == "__main__":
    unittest.main()
