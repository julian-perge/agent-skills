import unittest

from agent_skills import run
from fakes import FIXTURES

RUN_FIXTURES = FIXTURES / "run"


def summary_of(name: str) -> list[str]:
    text = (RUN_FIXTURES / f"{name}.txt").read_text(errors="replace")
    return run.digest(text.splitlines(keepends=True)).matches


def expected(name: str) -> list[str]:
    return (RUN_FIXTURES / f"{name}.summary").read_text().splitlines()


class RealOutputTest(unittest.TestCase):
    def test_each_fixture_gives_its_expected_summary(self) -> None:
        for name in ("pytest-failure", "gut-failure", "prek-failure", "test-blender-pass"):
            with self.subTest(fixture=name):
                lines = summary_of(name)
                self.assertEqual(lines, expected(name))
                self.assertLessEqual(len(lines), run.SUMMARY_LIMIT)

    def test_pytest_summary_has_the_count_and_the_failure(self) -> None:
        lines = summary_of("pytest-failure")
        self.assertIn("1 failed, 1 passed, 923 deselected in 22.46s", lines)
        self.assertTrue(any(line.startswith("FAILED tests/blender/test_region_import.py::") for line in lines))

    def test_gut_summary_has_the_script_error_the_failure_and_the_totals(self) -> None:
        lines = summary_of("gut-failure")
        self.assertIn('SCRIPT ERROR: Parse Error: Static function "money_levels()" not found in base "BattleRewards".', lines)
        self.assertIn("- test_victory_money_counts_the_companion_markers", lines)
        self.assertIn("Failing Tests         1", lines)
        self.assertTrue(any("[Failed]:  [130.0] expected to equal [36.0]" in line for line in lines))

    def test_prek_summary_names_the_failed_hook(self) -> None:
        self.assertEqual(summary_of("prek-failure")[-1], "- hook id: ruff-format")

    def test_blender_pass_keeps_the_count_line(self) -> None:
        self.assertEqual(summary_of("test-blender-pass"), ["9 passed, 896 deselected in 0.88s"])


class DigestTest(unittest.TestCase):
    def test_duplicates_are_dropped_and_order_is_kept(self) -> None:
        lines = ["FAILED a", "noise", "FAILED b", "FAILED a", "fatal: x"]
        self.assertEqual(run.digest(lines).matches, ["FAILED a", "FAILED b", "fatal: x"])

    def test_more_than_40_matches_keeps_the_last_40_and_says_so(self) -> None:
        result = run.digest([f"FAILED test_{i}" for i in range(50)] + ["3 failed in 1.0s"])
        rendered = result.render()
        self.assertIn("## Summary lines (last 40 of 51)", rendered)
        self.assertNotIn("FAILED test_10\n", rendered)
        self.assertIn("FAILED test_11\n", rendered)
        self.assertIn("3 failed in 1.0s\n", rendered)

    def test_ansi_codes_do_not_hide_a_match(self) -> None:
        self.assertEqual(run.digest(["\x1b[31m    [Failed]:  \x1b[0mboom\n"]).matches, ["    [Failed]:  boom"])

    def test_plain_output_has_no_summary_lines(self) -> None:
        self.assertEqual(run.digest(["Compiling foo", "done"]).matches, [])


if __name__ == "__main__":
    unittest.main()
