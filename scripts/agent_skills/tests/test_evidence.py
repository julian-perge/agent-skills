import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_skills import cli, land
from fakes import FakeRunner, fixture_text, names_repo

URCHIN = "julian-perge/urchin"
COMMIT = "5c1f0e7a9b2d4c6e8f0a1b3c5d7e9f1a2b4c6d8e"
PARENT = "0a1b2c3d4e5f60718293a4b5c6d7e8f901234567"
SECTIONS = """## Checks

`agent-skills land` runs each command on the PR branch before it merges.

- `just gut`
- `just pytest`

## Evidence paths

A pull request that changes one of these paths shows a screenshot of the real game.

Verify command: the verify-urchin skill

- `scenes/**`
- `scripts/ui/**`
- `assets/ui/**`
"""
WORKFLOW = fixture_text("workflow-urchin.md") + SECTIONS
IMAGE = "![inventory](https://github.com/julian-perge/urchin/blob/abc/pr-326/inventory.png?raw=true)"


def pull_json(name: str, **changes: object) -> str:
    data = json.loads(fixture_text(name))
    data["data"]["repository"]["pullRequest"].update(changes)
    return json.dumps(data)


class GlobTest(unittest.TestCase):
    def matches(self, glob: str, path: str) -> bool:
        return bool(land.touched([path], [glob]))

    def test_two_stars_cross_folders(self) -> None:
        self.assertTrue(self.matches("scenes/**", "scenes/ui/menu/inventory_window.tscn"))
        self.assertFalse(self.matches("scenes/**", "test/scenes/a.tscn"))

    def test_one_star_stays_in_its_folder(self) -> None:
        self.assertTrue(self.matches("scripts/ui/*.gd", "scripts/ui/hotbar.gd"))
        self.assertFalse(self.matches("scripts/ui/*.gd", "scripts/ui/menu/hotbar.gd"))

    def test_two_stars_and_a_slash_also_match_no_folder(self) -> None:
        self.assertTrue(self.matches("**/*.tscn", "main.tscn"))
        self.assertTrue(self.matches("**/*.tscn", "scenes/battle/vfx/bolt.tscn"))

    def test_a_glob_that_ends_with_a_slash_covers_the_folder(self) -> None:
        self.assertTrue(self.matches("assets/ui/", "assets/ui/menu/exp_fill.png"))
        self.assertFalse(self.matches("assets/ui/", "assets/uix/a.png"))

    def test_a_dot_is_a_dot_and_a_question_mark_is_one_character(self) -> None:
        self.assertFalse(self.matches("project.godot", "projectxgodot"))
        self.assertTrue(self.matches("icon?.png", "icon1.png"))
        self.assertFalse(self.matches("icon?.png", "icon/.png"))


class WorkflowTest(unittest.TestCase):
    def test_checks_are_the_backticked_list_items(self) -> None:
        self.assertEqual(land.checks(WORKFLOW), ("just gut", "just pytest"))

    def test_no_heading_gives_no_checks(self) -> None:
        self.assertEqual(land.checks(fixture_text("workflow-urchin.md")), ())

    def test_a_heading_matches_without_case_and_ends_at_the_next_one(self) -> None:
        self.assertEqual(land.checks("## checks\n- `a`\n## Other\n- `b`\n"), ("a",))

    def test_evidence_reads_the_globs_and_the_verify_command(self) -> None:
        found = land.evidence(WORKFLOW, ["scripts/ui/hotbar.gd", "dev/tests/test_a.py"], "")
        self.assertEqual(found, land.Evidence(True, ("scripts/ui/hotbar.gd",), 0, "the verify-urchin skill"))
        self.assertTrue(found.missing)

    def test_no_evidence_heading_is_not_configured(self) -> None:
        found = land.evidence(fixture_text("workflow-urchin.md"), ["scenes/a.tscn"], "")
        self.assertEqual(found, land.Evidence(False))
        self.assertFalse(found.missing)


class VerificationImagesTest(unittest.TestCase):
    def test_a_body_without_the_section_has_none(self) -> None:
        self.assertEqual(land.verification_images(f"Closes #1\n\n{IMAGE}\n"), 0)

    def test_a_markdown_image_and_an_img_tag_count(self) -> None:
        body = f'## Verification\n\n{IMAGE}\n\n<img width="400" src="https://example.com/a.png">\n'
        self.assertEqual(land.verification_images(body), 2)

    def test_a_local_path_and_a_plain_link_do_not_count(self) -> None:
        body = "## Verification\n\nScreenshots are in `~/tmp/v491/evidence/006.png`, see [the run](https://example.com/run).\n"
        self.assertEqual(land.verification_images(body), 0)

    def test_the_section_ends_at_the_next_heading_of_its_level(self) -> None:
        body = f"## Verification\n\n### Before\n\n{IMAGE}\n\n## Notes\n\n{IMAGE}\n"
        self.assertEqual(land.verification_images(body), 1)


class WithImagesTest(unittest.TestCase):
    def test_a_body_without_the_section_gets_one_at_its_end(self) -> None:
        self.assertEqual(
            land.with_images("Closes #227\n\nText.\n", [("a", "https://x/a.png")]),
            "Closes #227\n\nText.\n\n## Verification\n\n![a](https://x/a.png)\n",
        )

    def test_images_go_to_the_end_of_the_section(self) -> None:
        body = "Intro\n\n## Verification\n\n`just gut` passes.\n\n## Notes\n\nKeep.\n"
        self.assertEqual(
            land.with_images(body, [("a", "https://x/a.png"), ("b", "https://x/b.png")]),
            "Intro\n\n## Verification\n\n`just gut` passes.\n\n![a](https://x/a.png)\n\n![b](https://x/b.png)\n\n## Notes\n\nKeep.\n",
        )

    def test_windows_line_ends_stay(self) -> None:
        self.assertEqual(land.with_images("Closes #1\r\n", [("a", "https://x/a.png")]), "Closes #1\r\n\r\n## Verification\r\n\r\n![a](https://x/a.png)\r\n")

    def test_the_result_passes_the_gate(self) -> None:
        self.assertEqual(land.verification_images(land.with_images("Closes #1\n", [("a", "https://x/a.png")])), 1)


class EvidenceCase(unittest.TestCase):
    def setUp(self) -> None:
        checkout = tempfile.TemporaryDirectory()
        self.addCleanup(checkout.cleanup)
        self.root = Path(checkout.name)
        (self.root / "docs" / "agents").mkdir(parents=True)
        self.write_workflow(WORKFLOW)

    def write_workflow(self, text: str) -> None:
        (self.root / "docs" / "agents" / "workflow.md").write_text(text)

    def runner(self, *pulls: str) -> FakeRunner:
        runner = FakeRunner().on("git", "rev-parse", "--show-toplevel", stdout=f"{self.root}\n")
        for pull in pulls:
            runner.on("gh", "api", "graphql", stdout=pull)
        return runner

    def run_cli(self, argv: list[str], runner: FakeRunner) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--repo", URCHIN, *argv], runner)
        return code, out.getvalue(), err.getvalue()


class EvidenceVerbTest(EvidenceCase):
    def test_the_two_pull_requests_that_needed_a_screenshot_exit_1(self) -> None:
        for number, path in ((326, "assets/ui/menu/exp_fill.png"), (328, "assets/ui/")):
            with self.subTest(pr=number):
                code, out, err = self.run_cli(["evidence", str(number)], self.runner(pull_json(f"land-urchin-{number}.json")))
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertIn(f"PR #{number} needs evidence: it changes", err)
                self.assertIn(path, err)
                self.assertIn("Make the screenshots with the verify-urchin skill.", err)
                self.assertIn(f"agent-skills evidence {number} --add <image>...", err)

    def test_an_image_in_the_verification_section_passes(self) -> None:
        body = f"Closes #227\n\n## Verification\n\n{IMAGE}\n"
        code, out, _ = self.run_cli(["evidence", "326"], self.runner(pull_json("land-urchin-326.json", body=body)))
        self.assertEqual(code, 0)
        self.assertIn("PR #326 has evidence: it changes 9 evidence paths, and its `## Verification` section has 1 image.", out)

    def test_a_pull_request_that_changes_no_evidence_path_passes(self) -> None:
        files = {"totalCount": 1, "nodes": [{"path": "dev/tests/test_menu_math.py"}]}
        code, out, _ = self.run_cli(["evidence", "326"], self.runner(pull_json("land-urchin-326.json", files=files)))
        self.assertEqual(code, 0)
        self.assertEqual(out, "PR #326 needs no evidence: it changes no evidence path.\n")

    def test_a_repo_without_the_heading_passes(self) -> None:
        self.write_workflow(fixture_text("workflow-urchin.md"))
        code, out, _ = self.run_cli(["evidence", "326"], self.runner(pull_json("land-urchin-326.json")))
        self.assertEqual(code, 0)
        self.assertIn("no `## Evidence paths` heading", out)

    def test_a_repo_without_the_workflow_file_is_an_environment_error(self) -> None:
        (self.root / "docs" / "agents" / "workflow.md").unlink()
        runner = self.runner()
        code, _, err = self.run_cli(["evidence", "326"], runner)
        self.assertEqual(code, 2)
        self.assertIn("No docs/agents/workflow.md", err)
        self.assertEqual(runner.gh_calls(), [])

    def test_one_gh_call_that_names_the_repo(self) -> None:
        runner = self.runner(pull_json("land-urchin-326.json"))
        self.run_cli(["evidence", "326"], runner)
        self.assertEqual(len(runner.gh_calls()), 1)
        self.assertTrue(names_repo(runner.gh_calls()[0], URCHIN))

    def test_more_than_100_files_are_read_from_the_files_endpoint(self) -> None:
        files = {"totalCount": 101, "nodes": [{"path": "dev/a.py"}]}
        runner = self.runner(pull_json("land-urchin-326.json", files=files))
        runner.on("gh", "api", "--paginate", f"repos/{URCHIN}/pulls/326/files", stdout="dev/a.py\nscenes/late.tscn\n")
        code, _, err = self.run_cli(["evidence", "326"], runner)
        self.assertEqual(code, 1)
        self.assertIn("scenes/late.tscn", err)


class AddEvidenceTest(EvidenceCase):
    def images(self, *names: str) -> list[str]:
        paths = []
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x89PNG")
            paths.append(str(path))
        return paths

    def push_runner(self, first: str, second: str, parent: str | None = PARENT) -> FakeRunner:
        runner = self.runner(first)
        runner.on("git", "ls-remote", "origin", "refs/heads/evidence", stdout=f"{parent}\trefs/heads/evidence\n" if parent else "")
        if parent:
            runner.on("git", "fetch", "origin", "refs/heads/evidence").on("env", "git", "read-tree", parent)
        runner.on("git", "hash-object", stdout="b10b\n").on("env", "git", "update-index")
        runner.on("env", "git", "write-tree", stdout="7ree\n").on("git", "commit-tree", stdout=f"{COMMIT}\n")
        runner.on("git", "push", "origin", f"{COMMIT}:refs/heads/evidence")
        return runner.on("gh", "api", "graphql", stdout=second).on("gh", "api", "PATCH")

    def test_the_image_goes_to_the_evidence_branch_and_into_the_body(self) -> None:
        pull = pull_json("land-urchin-326.json")
        runner = self.push_runner(pull, pull)
        code, out, err = self.run_cli(["evidence", "326", "--add", *self.images("shots/006 inventory.png")], runner)
        self.assertEqual((code, err), (0, ""))
        url = f"https://github.com/{URCHIN}/blob/{COMMIT}/pr-326/006%20inventory.png?raw=true"
        self.assertIn(url, out)
        calls = runner.calls
        self.assertIn(["git", "commit-tree", "7ree", "-p", PARENT, "-m", "Evidence for PR #326"], calls)
        cacheinfo = next(call for call in calls if "update-index" in call)
        self.assertEqual(cacheinfo[-1], "100644,b10b,pr-326/006 inventory.png")
        self.assertTrue(cacheinfo[1].startswith("GIT_INDEX_FILE="))
        patch = runner.gh_calls()[-1]
        self.assertTrue(names_repo(patch, URCHIN))
        old = json.loads(pull)["data"]["repository"]["pullRequest"]["body"]
        new = patch[patch.index("-f") + 1].removeprefix("body=")
        self.assertEqual(new, land.with_images(old, [("006 inventory", url)]))
        self.assertTrue(new.startswith(old.rstrip()))
        self.assertEqual(land.verification_images(new), 1)

    def test_the_first_image_of_a_repo_starts_the_branch(self) -> None:
        pull = pull_json("land-urchin-326.json")
        runner = self.push_runner(pull, pull, parent=None)
        code, _, _ = self.run_cli(["evidence", "326", "--add", *self.images("a.png")], runner)
        self.assertEqual(code, 0)
        self.assertIn(["git", "commit-tree", "7ree", "-m", "Evidence for PR #326"], runner.calls)
        self.assertFalse(any("read-tree" in call for call in runner.calls))

    def test_no_git_call_touches_the_checkout_or_its_index(self) -> None:
        pull = pull_json("land-urchin-326.json")
        runner = self.push_runner(pull, pull)
        self.run_cli(["evidence", "326", "--add", *self.images("a.png")], runner)
        for call in runner.git_calls():
            self.assertIn(call[1], ("rev-parse", "ls-remote", "fetch", "hash-object", "commit-tree", "push"), call)

    def test_a_file_that_is_not_an_image_adds_nothing(self) -> None:
        runner = self.runner(pull_json("land-urchin-326.json"))
        notes = self.root / "notes.txt"
        notes.write_text("x")
        code, _, err = self.run_cli(["evidence", "326", "--add", str(notes), str(self.root / "gone.png")], runner)
        self.assertEqual(code, 1)
        self.assertIn("notes.txt is not an image", err)
        self.assertIn("gone.png is not a file", err)
        self.assertEqual(len(runner.calls), 2)

    def test_two_files_with_one_name_add_nothing(self) -> None:
        runner = self.runner(pull_json("land-urchin-326.json"))
        code, _, err = self.run_cli(["evidence", "326", "--add", *self.images("a/shot.png", "b/shot.png")], runner)
        self.assertEqual(code, 1)
        self.assertIn("two files are named shot.png", err)

    def test_a_body_that_changed_while_it_ran_is_not_edited(self) -> None:
        runner = self.push_runner(pull_json("land-urchin-326.json"), pull_json("land-urchin-326.json", body="Edited meanwhile.\n"))
        code, _, err = self.run_cli(["evidence", "326", "--add", *self.images("a.png")], runner)
        self.assertEqual(code, 1)
        self.assertIn("the body of PR #326 changed while this ran", err)
        self.assertFalse(any("PATCH" in call for call in runner.calls))


if __name__ == "__main__":
    unittest.main()
