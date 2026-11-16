import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from agent_skills import cli
from agent_skills.tracker import ac_boxes, tick_boxes
from fakes import FakeRunner, fixture_text, names_repo

URCHIN = "julian-perge/urchin"
BLENDER = "julian-perge/blender-addon-rs317-667mqo-makeup"


def body_of(fixture: str) -> str:
    return json.loads(fixture_text(fixture))["data"]["repository"]["issue"]["body"]


def answer(body: str) -> str:
    return json.dumps({"data": {"repository": {"issue": {"body": body}}}})


class BoxesTest(unittest.TestCase):
    def test_urchin_215_has_six_open_boxes(self) -> None:
        boxes = ac_boxes(body_of("ac-urchin-215.json"))
        self.assertEqual(len(boxes), 6)
        self.assertFalse(any(box.ticked for box in boxes))
        self.assertTrue(boxes[0].text.startswith("The game starts on the title."))

    def test_the_section_ends_at_the_next_heading_or_bold_line(self) -> None:
        body = "## Acceptance criteria\n- [ ] a\n- [x] b\n## Verification\n- [ ] not a criterion\n"
        self.assertEqual([(box.ticked, box.text) for box in ac_boxes(body)], [(False, "a"), (True, "b")])
        body = "**Acceptance criteria:**\n* [ ] a\n**QA:**\n- [ ] not a criterion\n"
        self.assertEqual([box.text for box in ac_boxes(body)], ["a"])

    def test_no_section_gives_none(self) -> None:
        self.assertIsNone(ac_boxes("## What to build\n- [ ] a\n"))

    def test_ticking_changes_only_the_named_lines(self) -> None:
        body = body_of("ac-urchin-215.json")
        ticked = tick_boxes(body, ac_boxes(body), [2, 5])
        changed = [(old, new) for old, new in zip(body.splitlines(), ticked.splitlines()) if old != new]
        self.assertEqual(len(changed), 2)
        self.assertEqual(len(ticked), len(body))
        for old, new in changed:
            self.assertEqual(old.replace("- [ ]", "- [x]", 1), new)

    def test_crlf_line_ends_are_kept(self) -> None:
        body = "## Acceptance criteria\r\n- [ ] a\r\n- [ ] b\r\n"
        self.assertEqual(tick_boxes(body, ac_boxes(body), [2]), "## Acceptance criteria\r\n- [ ] a\r\n- [x] b\r\n")


class AcVerbTest(unittest.TestCase):
    def run_cli(self, argv: list[str], *bodies: str, edit_code: int = 0) -> tuple[int, str, str, FakeRunner]:
        runner = FakeRunner()
        for body in bodies:
            runner.on("gh", "api", "graphql", stdout=answer(body))
        runner.on("gh", "issue", "edit", stdout="https://github.com/x/y/issues/1\n", returncode=edit_code)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv, runner)
        return code, out.getvalue(), err.getvalue(), runner

    def edits(self, runner: FakeRunner) -> list[list[str]]:
        return [call for call in runner.gh_calls() if call[1:3] == ["issue", "edit"]]

    def test_the_list_form_prints_each_box_and_the_count_from_one_call(self) -> None:
        code, out, _, runner = self.run_cli(["--repo", BLENDER, "ac", "84"], body_of("ac-blender-84.json"))
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 5)
        self.assertTrue(lines[0].startswith("1. [ ] `docs/research/82-gltf-export.md` has rows 2 and 3 filled"))
        self.assertEqual(lines[-1], "Ticked: 0 of 4")
        self.assertEqual(len(runner.gh_calls()), 1)
        self.assertTrue(names_repo(runner.gh_calls()[0], BLENDER))

    def test_tick_writes_the_body_once_with_only_those_lines_changed(self) -> None:
        body = body_of("ac-urchin-215.json")
        code, out, _, runner = self.run_cli(["--repo", URCHIN, "ac", "215", "--tick", "1,3"], body, body)
        self.assertEqual(code, 0)
        edits = self.edits(runner)
        self.assertEqual(len(edits), 1)
        self.assertTrue(names_repo(edits[0], URCHIN))
        self.assertEqual(edits[0][edits[0].index("--body") + 1], tick_boxes(body, ac_boxes(body), [1, 3]))
        self.assertIn("1. [x] ", out)
        self.assertIn("2. [ ] ", out)
        self.assertTrue(out.endswith("Ticked: 2 of 6\n"))

    def test_a_ticked_box_stays_ticked_and_needs_no_write(self) -> None:
        body = "## Acceptance criteria\n- [x] a\n- [ ] b\n"
        code, out, _, runner = self.run_cli(["--repo", URCHIN, "ac", "1", "--tick", "1"], body, body)
        self.assertEqual(code, 0)
        self.assertEqual(self.edits(runner), [])
        self.assertIn("1. [x] a", out)

    def test_refusals_exit_1_and_write_nothing(self) -> None:
        cases = {
            "no section": ("## What to build\n- [ ] a\n", "1"),
            "no box": ("## Acceptance criteria\nNone yet.\n", "1"),
            "index too high": ("## Acceptance criteria\n- [ ] a\n", "2"),
            "index zero": ("## Acceptance criteria\n- [ ] a\n", "0"),
        }
        for name, (body, ticks) in cases.items():
            with self.subTest(name):
                code, _, err, runner = self.run_cli(["--repo", URCHIN, "ac", "1", "--tick", ticks], body, body)
                self.assertEqual(code, 1)
                self.assertTrue(err)
                self.assertEqual(self.edits(runner), [])

    def test_a_body_that_changed_between_the_reads_is_not_written(self) -> None:
        body = "## Acceptance criteria\n- [ ] a\n"
        code, _, err, runner = self.run_cli(["--repo", URCHIN, "ac", "1", "--tick", "1"], body, body + "\nedited\n")
        self.assertEqual(code, 1)
        self.assertIn("changed", err)
        self.assertEqual(self.edits(runner), [])

    def test_the_list_form_of_an_issue_with_no_section_exits_1(self) -> None:
        code, _, err, _ = self.run_cli(["--repo", URCHIN, "ac", "1"], "no criteria here")
        self.assertEqual(code, 1)
        self.assertIn("Acceptance criteria", err)

    def test_a_tick_list_that_is_not_numbers_is_a_usage_error(self) -> None:
        code, _, _, runner = self.run_cli(["--repo", URCHIN, "ac", "1", "--tick", "a,b"])
        self.assertEqual(code, 2)
        self.assertEqual(runner.calls, [])


if __name__ == "__main__":
    unittest.main()
