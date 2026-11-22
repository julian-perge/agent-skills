import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from agent_skills import cli, land
from fakes import FakeRunner, fixture_text, names_repo
from gitrepo import RealGit, clone, commit, git, hermetic, new_origin

URCHIN = "julian-perge/urchin"
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

    def test_two_stars_inside_a_name_do_not_swallow_the_slash(self) -> None:
        self.assertFalse(self.matches("a**/b", "ab"))
        self.assertTrue(self.matches("a**/b", "a/x/b"))

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

    def test_a_heading_inside_a_code_fence_is_not_the_section(self) -> None:
        text = "## Review\n\n```\n## Checks\n- `fake`\n```\n\n## Checks\n\n- `real`\n"
        self.assertEqual(land.checks(text), ("real",))

    def test_list_items_that_would_be_skipped_or_misread_are_problems(self) -> None:
        text = "## Checks\n1. `just a`\n+ `just b`\n- `just a && just b`\n- ` `\n- `bash -c 'just a && just b'`\n## Evidence paths\n- `scenes/*.{tscn,gd}`\n* `scenes/**`\n"
        problems = land.workflow_problems(text)
        self.assertEqual(len(problems), 5)
        self.assertIn("'1. `just a`' is not one command in backticks", problems[0])
        self.assertIn("'+ `just b`' is not one command in backticks", problems[1])
        self.assertIn("uses shell syntax, and a command runs without a shell.", problems[2])
        self.assertIn("is empty.", problems[3])
        self.assertIn("uses [ ], { } or a backslash", problems[4])

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

    def test_an_image_that_github_cannot_show_does_not_count(self) -> None:
        body = "## Verification\n\n![a](~/tmp/a.png)\n\n`![b](https://x/b.png)`\n\n```\n![c](https://x/c.png)\n```\n"
        self.assertEqual(land.verification_images(body), 0)

    def test_a_comment_line_in_a_code_fence_does_not_end_the_section(self) -> None:
        body = f"## Verification\n\n```bash\n# run the game\njust godot\n```\n\n{IMAGE}\n\n## Notes\n"
        self.assertEqual(land.verification_images(body), 1)

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

    def test_images_go_after_a_code_fence_and_not_into_it(self) -> None:
        body = "## Verification\n\n```bash\n# run the game\n```\n\n## Notes\n"
        self.assertEqual(
            land.with_images(body, [("a", "https://x/a.png")]),
            "## Verification\n\n```bash\n# run the game\n```\n\n![a](https://x/a.png)\n\n## Notes\n",
        )

    def test_a_body_with_mixed_line_ends_keeps_each_line_and_its_one_section(self) -> None:
        new = land.with_images("Intro\r\n\r\n## Verification\n\ntext\n\n## Notes\n", [("a", "https://x/a.png")])
        self.assertEqual(new, "Intro\r\n\r\n## Verification\n\ntext\n\r\n![a](https://x/a.png)\r\n\r\n## Notes\n")
        self.assertEqual(land.verification_images(new), 1)

    def test_brackets_in_a_file_name_do_not_break_the_image(self) -> None:
        new = land.with_images("", [("shot[1]", "https://x/shot%5B1%5D.png")])
        self.assertEqual(new, "## Verification\n\n![shot(1)](https://x/shot%5B1%5D.png)\n")
        self.assertEqual(land.verification_images(new), 1)

    def test_windows_line_ends_stay(self) -> None:
        self.assertEqual(land.with_images("Closes #1\r\n", [("a", "https://x/a.png")]), "Closes #1\r\n\r\n## Verification\r\n\r\n![a](https://x/a.png)\r\n")

    def test_the_result_passes_the_gate(self) -> None:
        self.assertEqual(land.verification_images(land.with_images("Closes #1\n", [("a", "https://x/a.png")])), 1)


class EvidenceVerbTest(unittest.TestCase):
    def setUp(self) -> None:
        checkout = tempfile.TemporaryDirectory()
        self.addCleanup(checkout.cleanup)
        self.root = Path(checkout.name)

    def runner(self, pull: str, base: str | None = WORKFLOW) -> FakeRunner:
        """The calls of `evidence`, in its order. `base` is docs/agents/workflow.md on the base branch, or None when it has none."""
        runner = FakeRunner().on("gh", "api", "graphql", stdout=pull).on("git", "rev-parse", "--show-toplevel", stdout=f"{self.root}\n")
        runner.on("git", "fetch", "--prune", "origin").on("git", "rev-parse", "--verify", "--quiet")
        return runner.on("git", "show", "origin/main:docs/agents/workflow.md", stdout=base or "", returncode=0 if base else 128)

    def run_cli(self, argv: list[str], runner: FakeRunner) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--repo", URCHIN, *argv], runner)
        return code, out.getvalue(), err.getvalue()

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
        code, out, err = self.run_cli(["evidence", "326"], self.runner(pull_json("land-urchin-326.json", body=body)))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, "PR #326 has evidence: it changes 9 evidence paths, and its `## Verification` section has 1 image.\n")

    def test_a_pull_request_that_changes_no_evidence_path_passes(self) -> None:
        files = {"totalCount": 1, "nodes": [{"path": "dev/tests/test_menu_math.py"}]}
        code, out, _ = self.run_cli(["evidence", "326"], self.runner(pull_json("land-urchin-326.json", files=files)))
        self.assertEqual(code, 0)
        self.assertEqual(out, "PR #326 needs no evidence: it changes no evidence path.\n")

    def test_a_repo_without_the_heading_passes(self) -> None:
        code, out, _ = self.run_cli(["evidence", "326"], self.runner(pull_json("land-urchin-326.json"), fixture_text("workflow-urchin.md")))
        self.assertEqual(code, 0)
        self.assertIn("no `## Evidence paths` heading", out)

    def test_the_rules_come_from_the_base_branch_and_not_from_the_checkout(self) -> None:
        (self.root / "docs" / "agents").mkdir(parents=True)
        (self.root / "docs" / "agents" / "workflow.md").write_text(fixture_text("workflow-urchin.md"))
        files = {"totalCount": 2, "nodes": [{"path": "docs/agents/workflow.md"}, {"path": "scenes/a.tscn"}]}
        code, _, err = self.run_cli(["evidence", "326"], self.runner(pull_json("land-urchin-326.json", files=files)))
        self.assertEqual(code, 1)
        self.assertIn("Note: this pull request changes docs/agents/workflow.md. The gate comes from main.\n", err)
        self.assertIn("it changes 1 evidence path (scenes/a.tscn)", err)

    def test_a_base_branch_without_the_file_gives_the_file_of_the_checkout(self) -> None:
        (self.root / "docs" / "agents").mkdir(parents=True)
        (self.root / "docs" / "agents" / "workflow.md").write_text(WORKFLOW)
        code, _, err = self.run_cli(["evidence", "326"], self.runner(pull_json("land-urchin-326.json"), base=None))
        self.assertEqual(code, 1)
        self.assertIn("Note: main has no docs/agents/workflow.md yet, so the gate comes from this checkout.\n", err)

    def test_no_workflow_file_at_all_is_an_environment_error(self) -> None:
        code, _, err = self.run_cli(["evidence", "326"], self.runner(pull_json("land-urchin-326.json"), base=None))
        self.assertEqual(code, 2)
        self.assertIn("No docs/agents/workflow.md", err)

    def test_a_list_item_that_cannot_be_read_is_an_environment_error(self) -> None:
        base = WORKFLOW.replace("- `scenes/**`", "- `/scenes/**`\n- `scripts/[a-z]*.gd`\n- `<glob>`").replace("- `just gut`", "- `just gut` (fast)")
        code, out, err = self.run_cli(["evidence", "326"], self.runner(pull_json("land-urchin-326.json"), base))
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err.splitlines(), [
            "docs/agents/workflow.md has list items that cannot be read:",
            "- under `## Checks`, the list item '- `just gut` (fast)' is not one command in backticks with nothing after it.",
            "- under `## Evidence paths`, the list item '- `/scenes/**`' must start at the repo root with no leading / or ./.",
            "- under `## Evidence paths`, the list item '- `scripts/[a-z]*.gd`' uses [ ], { } or a backslash, and only *, ** and ? are read.",
            "- under `## Evidence paths`, the list item '- `<glob>`' is the placeholder of the seed, not a glob.",
        ])

    def test_one_gh_call_that_names_the_repo(self) -> None:
        runner = self.runner(pull_json("land-urchin-326.json"))
        self.run_cli(["evidence", "326"], runner)
        self.assertEqual(len(runner.gh_calls()), 1)
        self.assertTrue(names_repo(runner.gh_calls()[0], URCHIN))

    def test_more_than_100_files_are_read_from_the_files_endpoint(self) -> None:
        files = {"totalCount": 101, "nodes": [{"path": "dev/a.py"}]}
        runner = FakeRunner().on("gh", "api", "--paginate", f"repos/{URCHIN}/pulls/326/files", stdout="dev/a.py\nscenes/late.tscn\n")
        runner.rules += self.runner(pull_json("land-urchin-326.json", files=files)).rules
        code, _, err = self.run_cli(["evidence", "326"], runner)
        self.assertEqual(code, 1)
        self.assertIn("scenes/late.tscn", err)


class AddEvidenceTest(unittest.TestCase):
    """Runs `evidence --add` with real git against a local bare repo. Only gh is faked."""

    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name).resolve()
        env = hermetic()
        env.start()
        self.addCleanup(env.stop)
        self.origin, self.work = new_origin(self.folder, {"README.md": "x\n"})
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.work)
        self.pull = pull_json("land-urchin-326.json")
        self.body = json.loads(self.pull)["data"]["repository"]["pullRequest"]["body"]

    def image(self, name: str, data: bytes = b"\x89PNG\r\n\x1a\n") -> str:
        path = self.folder / "shots" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def add(self, *images: str, repo: str = URCHIN, body_now: str | None = None) -> tuple[int, str, str, RealGit]:
        runner = RealGit()
        now = json.dumps({"data": {"repository": {"pullRequest": {"body": self.body if body_now is None else body_now}}}})
        runner.gh.on("gh", "api", "graphql", stdout=self.pull).on("gh", "api", "graphql", stdout=now).on("gh", "api", "PATCH")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--repo", repo, "evidence", "326", "--add", *images], runner)
        return code, out.getvalue(), err.getvalue(), runner

    def on_origin(self, *args: str) -> str:
        return git(self.origin, *args)

    def test_the_image_goes_to_the_evidence_branch_and_into_the_body(self) -> None:
        code, out, err, runner = self.add(self.image("006 inventory.png"))
        self.assertEqual((code, err), (0, ""))
        commit = self.on_origin("rev-parse", "evidence")
        url = f"https://github.com/{URCHIN}/blob/{commit}/pr-326/006%20inventory.png?raw=true"
        self.assertEqual(out, f"Added 1 image to the `## Verification` section of PR #326, from the evidence branch at {commit[:8]}:\n{url}\n")
        self.assertEqual(self.on_origin("ls-tree", "-r", "--name-only", "evidence"), "pr-326/006 inventory.png")
        self.assertEqual(self.on_origin("log", "-1", "--format=%s%n%P", "evidence"), "Evidence for PR #326")
        stored = subprocess.run(["git", "cat-file", "blob", "evidence:pr-326/006 inventory.png"], cwd=self.origin, capture_output=True).stdout
        self.assertEqual(stored, b"\x89PNG\r\n\x1a\n")
        patch = runner.gh_calls()[-1]
        self.assertEqual(patch[:5], ["gh", "api", "--method", "PATCH", f"repos/{URCHIN}/pulls/326"])
        new = patch[patch.index("-f") + 1].removeprefix("body=")
        self.assertEqual(new, self.body.rstrip() + f"\n\n## Verification\n\n![006 inventory]({url})\n")
        self.assertEqual(land.verification_images(new), 1)

    def test_the_checkout_its_index_and_its_hooks_are_not_used(self) -> None:
        (self.work / "staged.txt").write_text("staged\n")
        git(self.work, "add", "staged.txt")
        (self.work / "README.md").write_text("changed\n")
        hook = self.work / ".git" / "hooks" / "pre-push"
        hook.write_text(f"#!/bin/sh\ntouch {self.folder / 'hook-ran'}\n")
        hook.chmod(0o755)
        before = ((self.work / ".git" / "index").read_bytes(), git(self.work, "status", "--porcelain", "--branch"), git(self.work, "rev-parse", "HEAD"))
        code, _, _, runner = self.add(self.image("a.png"))
        self.assertEqual(code, 0)
        after = ((self.work / ".git" / "index").read_bytes(), git(self.work, "status", "--porcelain", "--branch"), git(self.work, "rev-parse", "HEAD"))
        self.assertEqual(before, after)
        self.assertFalse((self.folder / "hook-ran").exists())
        commit = self.on_origin("rev-parse", "evidence")
        self.assertIn(["git", "push", "--no-verify", "origin", f"{commit}:refs/heads/evidence"], runner.calls)

    def test_a_second_run_adds_a_commit_on_top_and_keeps_the_older_images(self) -> None:
        self.add(self.image("a.png"))
        first = self.on_origin("rev-parse", "evidence")
        code, _, _, _ = self.add(self.image("b.png", b"second"))
        self.assertEqual(code, 0)
        self.assertEqual(self.on_origin("rev-parse", "evidence^"), first)
        self.assertEqual(self.on_origin("ls-tree", "-r", "--name-only", "evidence").splitlines(), ["pr-326/a.png", "pr-326/b.png"])

    def test_a_push_from_another_session_is_not_overwritten(self) -> None:
        self.add(self.image("a.png"))
        other = self.folder / "other"
        git(self.folder, "clone", "-q", "-b", "evidence", str(self.origin), str(other))
        theirs = commit(other, {"pr-9/theirs.png": "x"}, "Evidence for PR #9")
        runner = RealGit()
        runner.gh.on("gh", "api", "graphql", stdout=self.pull)
        real = runner.__call__

        def push_between(argv: list[str]) -> object:
            if argv[:2] == ["git", "commit-tree"]:
                git(other, "push", "-q", "origin", "evidence")
            return real(argv)

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--repo", URCHIN, "evidence", "326", "--add", self.image("b.png")], push_between)
        self.assertEqual(code, 2)
        self.assertEqual(self.on_origin("rev-parse", "evidence"), theirs)
        self.assertEqual(len(runner.gh_calls()), 1)

    def test_a_clone_that_lacks_the_evidence_branch_adds_on_top_of_it(self) -> None:
        second = clone(self.origin, self.folder / "second")
        self.add(self.image("a.png"))
        os.chdir(second)
        code, _, _, _ = self.add(self.image("b.png", b"second"))
        self.assertEqual(code, 0)
        self.assertEqual(self.on_origin("ls-tree", "-r", "--name-only", "evidence").splitlines(), ["pr-326/a.png", "pr-326/b.png"])

    def test_a_body_with_windows_line_ends_keeps_them(self) -> None:
        self.body = "Closes #227\r\n\r\nText.\r\n"
        self.pull = pull_json("land-urchin-326.json", body=self.body)
        code, out, _, runner = self.add(self.image("a.png"))
        self.assertEqual(code, 0)
        patch = runner.gh_calls()[-1]
        url = out.splitlines()[-1]
        self.assertEqual(patch[patch.index("-f") + 1], f"body=Closes #227\r\n\r\nText.\r\n\r\n## Verification\r\n\r\n![a]({url})\r\n")

    def test_a_file_that_is_not_an_image_adds_nothing(self) -> None:
        notes = self.folder / "notes.txt"
        notes.write_text("x")
        code, _, err, runner = self.add(str(notes), str(self.folder / "gone.png"))
        self.assertEqual(code, 1)
        self.assertIn("notes.txt is not an image", err)
        self.assertIn("gone.png is not a file", err)
        self.assertEqual(len(runner.calls), 1)

    def test_two_files_with_one_name_add_nothing(self) -> None:
        code, _, err, runner = self.add(self.image("a/shot.png"), self.image("b/shot.png"))
        self.assertEqual(code, 1)
        self.assertIn("two files are named shot.png", err)
        self.assertEqual(len(runner.calls), 1)

    def test_a_repo_flag_that_is_not_origin_adds_nothing(self) -> None:
        code, _, err, runner = self.add(self.image("a.png"), repo="julian-perge/blender")
        self.assertEqual(code, 1)
        self.assertIn("the images would go to origin (julian-perge/urchin) and the links to julian-perge/blender", err)
        self.assertFalse(any("push" in call for call in runner.calls))

    def test_a_body_that_changed_while_it_ran_is_not_edited(self) -> None:
        code, _, err, runner = self.add(self.image("a.png"), body_now="Edited meanwhile.\n")
        self.assertEqual(code, 1)
        self.assertIn("the body of PR #326 changed while this ran", err)
        self.assertEqual(len(runner.gh_calls()), 2)


if __name__ == "__main__":
    unittest.main()
