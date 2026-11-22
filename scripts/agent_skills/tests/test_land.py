import io
import json
import os
import sys
import tempfile
import unittest
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from agent_skills import cli, land
from agent_skills.github import LAND_QUERY, parse_worktrees
from fakes import fixture_text, names_repo
from gitrepo import RealGit, commit, git, hermetic, new_origin

URCHIN = "julian-perge/urchin"
HEAD = "6baf62c2ba12fbdb9f53609af6710f6bcfa45b55"
BRANCH = "fix/227-inventory-doll"
DECISION = "### Decisions from the review of PR #326\n\n- No findings."
OPEN = land.LandPull(326, "Place the doll", base="main", head=BRANCH, head_commit=HEAD, comments=(DECISION,))
NO_EVIDENCE = land.Evidence(configured=False)
GATE = "docs/agents/workflow.md"


def workflow(items: str) -> str:
    return f"# Workflow\n\n## Checks\n\n{items}"


def refusals(pull: land.LandPull = OPEN, branch: str = BRANCH, commit: str = HEAD, dirty: bool = False, behind: int = 0,
             found: land.Evidence = NO_EVIDENCE, commands: tuple[str, ...] = ("just gut",)) -> list[str]:
    return land.refusals(pull, branch, commit, dirty, behind, found, commands)


def changed(**fields: object) -> land.LandPull:
    return land.LandPull(**{**OPEN.__dict__, **fields})


class RefusalsTest(unittest.TestCase):
    def test_a_ready_pull_request_has_none(self) -> None:
        self.assertEqual(refusals(), [])

    def test_a_merged_pull_request_gives_only_that_reason(self) -> None:
        self.assertEqual(refusals(changed(state="MERGED", comments=()), branch="main"), ["the pull request is merged."])

    def test_a_draft(self) -> None:
        self.assertEqual(refusals(changed(draft=True)), ["the pull request is a draft."])

    def test_another_branch(self) -> None:
        self.assertEqual(refusals(branch="main"), [f"this checkout is on main, not on the PR branch {BRANCH}. Run `gh pr checkout 326`."])

    def test_a_commit_that_is_not_the_head_of_the_pull_request(self) -> None:
        self.assertEqual(refusals(commit="1234567890abcdef"), ["HEAD is 12345678 and the pull request is at 6baf62c2. Push or pull until they are the same commit."])

    def test_a_tree_with_changes(self) -> None:
        self.assertEqual(refusals(dirty=True), ["the working tree has changes. Commit and push them, or stash them."])

    def test_a_branch_behind_its_base(self) -> None:
        self.assertEqual(
            refusals(behind=2),
            ["the PR branch is 2 commits behind main, so the checks would not test the merged code. Run `git merge origin/main`, push, and run the command again."],
        )

    def test_merge_conflicts(self) -> None:
        self.assertEqual(refusals(changed(mergeable="CONFLICTING")), ["the pull request has merge conflicts with main."])

    def test_an_unknown_merge_state(self) -> None:
        self.assertIn("has not worked out yet", refusals(changed(mergeable="UNKNOWN"))[0])

    def test_no_review_decision_comment(self) -> None:
        reasons = refusals(changed(comments=("### Decisions from the build of #227\n\n- a", "### Decisions from the review of PR #32\n\n- b")))
        self.assertEqual(
            reasons,
            ["no review decision comment names PR #326 on the pull request, on an issue it closes or on the parent of one. "
             "The review posts it with `agent-skills decide <issue or PR> --from review --pr 326`."],
        )

    def test_only_a_whole_first_line_is_a_review_decision(self) -> None:
        for body in ("### Decisions from the review of PR #3260", "### Decisions from the review of PR #326 are not made yet",
                     "Decisions pending. Later: decisions from the review of PR #326", "Notes\n### Decisions from the review of PR #326"):
            with self.subTest(body=body):
                self.assertFalse(land.has_review_decision(326, [body]))
        for body in (DECISION, "**Decisions from the review of PR #326**\n\n- a", "decisions from the review of pr #326"):
            with self.subTest(body=body):
                self.assertTrue(land.has_review_decision(326, [body]))

    def test_a_branch_that_is_not_the_pr_branch_gets_no_behind_reason(self) -> None:
        self.assertEqual(len(refusals(branch="main", behind=4)), 1)

    def test_missing_evidence(self) -> None:
        reasons = refusals(found=land.Evidence(True, ("scenes/a.tscn",), 0, "the verify-urchin skill"))
        self.assertEqual(
            reasons,
            ["it changes 1 evidence path (scenes/a.tscn), and its body has no `## Verification` section with an image. "
             "Make the screenshots with the verify-urchin skill. Then run `agent-skills evidence 326 --add <image>...`."],
        )

    def test_no_check_command(self) -> None:
        self.assertEqual(refusals(commands=()), ["docs/agents/workflow.md has no `## Checks` heading with a command, so the checks of the repo cannot run."])

    def test_every_reason_is_listed(self) -> None:
        self.assertEqual(len(refusals(changed(draft=True, mergeable="CONFLICTING", comments=()), dirty=True, behind=1, commands=())), 6)


class WorktreesTest(unittest.TestCase):
    def test_the_main_worktree_is_first_and_a_detached_one_has_no_branch(self) -> None:
        porcelain = (
            "worktree /home/j/code/urchin\nHEAD 2521519\nbranch refs/heads/main\n\n"
            "worktree /home/j/code/urchin/.claude/worktrees/a b\nHEAD 6baf62c\nbranch refs/heads/fix/227-inventory-doll\n\n"
            "worktree /tmp/x\nHEAD 1111111\ndetached\n"
        )
        self.assertEqual(
            parse_worktrees(porcelain),
            [("/home/j/code/urchin", "main"), ("/home/j/code/urchin/.claude/worktrees/a b", BRANCH), ("/tmp/x", None)],
        )


class LandCase(unittest.TestCase):
    """Runs `land` with real git: a bare origin, a clone on the PR branch, and a fake gh whose merge really merges on the origin."""

    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name).resolve()
        env = hermetic(TMPDIR=str(self.folder))
        env.start()
        self.addCleanup(env.stop)
        self.marker = self.folder / "check-ran"
        self.origin, self.work = new_origin(self.folder, {**self.base_files(), "app.txt": "one\n", ".gitignore": "ignored.env\n"})
        git(self.work, "switch", "-q", "-c", BRANCH)
        self.head = commit(self.work, {"app.txt": "two\n", **self.branch_files()}, "fix: the app (#227)")
        git(self.work, "push", "-q", "-u", "origin", BRANCH)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.work)

    def base_files(self) -> dict[str, str]:
        return {GATE: workflow(self.check("check-ran"))}

    def branch_files(self) -> dict[str, str]:
        return {}

    def check(self, marker: str, code: int = 0) -> str:
        """A list item for `## Checks` that writes its working directory to a marker file and exits with `code`."""
        path = self.folder / marker
        return f'- `{sys.executable} -c "import os, pathlib, sys; pathlib.Path({str(path)!r}).write_text(os.getcwd()); sys.exit({code})"`\n'

    def pull(self, **changes: object) -> str:
        data = json.loads(fixture_text("land-urchin-326.json"))
        files = {"totalCount": 1, "nodes": [{"path": "app.txt"}]}
        pull = {"state": "OPEN", "mergeable": "MERGEABLE", "headRefName": BRANCH, "headRefOid": self.head, "files": files, "body": "Closes #227\n", **changes}
        data["data"]["repository"]["pullRequest"].update(pull)
        return json.dumps(data)

    def merge_on_origin(self) -> None:
        side = self.folder / "merger"
        if not side.exists():
            git(self.folder, "clone", "-q", str(self.origin), str(side))
        git(side, "fetch", "-q", "origin")
        git(side, "switch", "-q", "main")
        git(side, "merge", "-q", "--no-ff", f"origin/{BRANCH}", "-m", "Merge pull request #326")
        git(side, "push", "-q", "origin", "main")
        git(side, "push", "-q", "origin", "--delete", BRANCH)

    def push_to_main(self) -> None:
        side = self.folder / "other"
        git(self.folder, "clone", "-q", str(self.origin), str(side))
        commit(side, {"other.txt": "x\n"}, "feat: another change")
        git(side, "push", "-q", "origin", "main")

    def runner(self, *pulls: str, merges: bool = True) -> RealGit:
        runner = RealGit(self.merge_on_origin if merges else None)
        for pull in pulls or (self.pull(),):
            runner.gh.on("gh", "api", "graphql", stdout=pull)
        return runner

    def land(self, runner: RealGit | None = None) -> tuple[int, str, str, RealGit]:
        runner = runner or self.merging()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch("agent_skills.cli.time.sleep") as self.sleep:
            code = cli.main(["--repo", URCHIN, "land", "326"], runner)
        return code, out.getvalue(), err.getvalue(), runner

    def merging(self, *pulls: str, on_merge: Callable[[], None] | None = None) -> RealGit:
        """A runner whose gh merges on the origin, runs `on_merge` after that, and then reports the pull request as merged."""
        def merge() -> None:
            self.merge_on_origin()
            if on_merge:
                on_merge()

        runner = RealGit(merge)
        for pull in pulls or (self.pull(),):
            runner.gh.on("gh", "api", "graphql", stdout=pull)
        runner.gh.on("gh", "pr", "merge").on("gh", "pr", "view", stdout="MERGED\n")
        return runner

    def merged(self, runner: RealGit) -> bool:
        return any(call[:3] == ["gh", "pr", "merge"] for call in runner.calls)

    def branches(self, repo: Path, *args: str) -> list[str]:
        return git(repo, "branch", "--format=%(refname:short)", *args).split()

    def assert_refused(self, reason: str, runner: RealGit | None = None, branch: str = BRANCH) -> str:
        """Exit 1 with the reason, and nothing ran or changed: no check, no merge, and both repos as they were."""
        code, out, err, runner = self.land(runner)
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err.splitlines()[0], "Not landed: PR #326")
        self.assertIn(f"- {reason}", err)
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.merged(runner))
        self.assertEqual(git(self.work, "branch", "--show-current"), branch)
        self.assertEqual(git(self.origin, "rev-parse", BRANCH), self.head)
        return err


class LandVerbTest(LandCase):
    def test_a_clean_pull_request_merges_and_the_checkout_ends_on_the_base_branch(self) -> None:
        code, out, err, runner = self.land()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.marker.read_text(), str(self.work))
        merge = git(self.origin, "rev-parse", "main")
        self.assertEqual(git(self.work, "branch", "--show-current"), "main")
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), merge)
        self.assertEqual(git(self.work, "log", "-1", "--format=%s"), "Merge pull request #326")
        self.assertEqual(self.branches(self.work, "--all"), ["main", "origin", "origin/main"])
        self.assertEqual(git(self.work, "status", "--porcelain"), "")
        self.assertIn(["gh", "pr", "merge", "326", "--repo", URCHIN, "--merge", "--delete-branch", "--match-head-commit", self.head], runner.calls)
        self.assertTrue(out.endswith(
            "Landed PR #326 into main: https://github.com/julian-perge/urchin/pull/326\n"
            f"This checkout is on main at {merge[:7]}.\nDeleted the local branch {BRANCH}.\n"
        ))
        self.assertTrue(all(names_repo(call, URCHIN) for call in runner.gh_calls()))

    def test_the_checks_run_in_the_repo_root(self) -> None:
        (self.work / "sub").mkdir()
        os.chdir(self.work / "sub")
        code, _, _, _ = self.land()
        self.assertEqual(code, 0)
        self.assertEqual(self.marker.read_text(), str(self.work))

    def test_a_draft_is_refused(self) -> None:
        self.assert_refused("the pull request is a draft.", self.runner(self.pull(isDraft=True)))

    def test_a_merged_pull_request_is_refused(self) -> None:
        err = self.assert_refused("the pull request is merged.", self.runner(self.pull(state="MERGED")))
        self.assertEqual(len(err.splitlines()), 2)

    def test_a_checkout_on_another_branch_is_refused(self) -> None:
        git(self.work, "switch", "-q", "main")
        self.assert_refused(f"this checkout is on main, not on the PR branch {BRANCH}.", branch="main")

    def test_a_checkout_that_is_not_at_the_head_of_the_pull_request_is_refused(self) -> None:
        self.assert_refused(f"HEAD is {self.head[:8]} and the pull request is at 11111111.", self.runner(self.pull(headRefOid="1" * 40)))

    def test_a_changed_tracked_file_is_refused(self) -> None:
        (self.work / "app.txt").write_text("not committed\n")
        self.assert_refused("the working tree has changes.")

    def test_a_branch_behind_its_base_is_refused(self) -> None:
        self.push_to_main()
        self.assert_refused("the PR branch is 1 commit behind main, so the checks would not test the merged code.")

    def test_merge_conflicts_are_refused(self) -> None:
        self.assert_refused("the pull request has merge conflicts with main.", self.runner(self.pull(mergeable="CONFLICTING")))

    def test_an_unknown_merge_state_is_read_5_times_and_then_refused(self) -> None:
        runner = self.runner(*[self.pull(mergeable="UNKNOWN")] * 5)
        self.assert_refused("GitHub has not worked out yet whether the pull request merges cleanly.", runner)
        self.assertEqual(len(runner.gh_calls()), 5)
        self.assertEqual(self.sleep.call_args_list, [mock.call(2)] * 4)

    def test_an_unknown_merge_state_that_settles_goes_on(self) -> None:
        code, _, _, runner = self.land(self.merging(self.pull(mergeable="UNKNOWN"), self.pull()))
        self.assertEqual(code, 0)
        self.sleep.assert_called_once_with(2)

    def test_no_review_decision_comment_is_refused(self) -> None:
        issue = {"comments": {"nodes": [{"body": "### Decisions from the build of #227\n\n- a"}]}, "parent": None}
        self.assert_refused("no review decision comment names PR #326", self.runner(self.pull(closingIssuesReferences={"nodes": [issue]})))

    def test_a_decision_comment_on_the_parent_issue_counts(self) -> None:
        issue = {"comments": {"nodes": []}, "parent": {"comments": {"nodes": [{"body": DECISION}]}}}
        code, _, _, runner = self.land(self.merging(self.pull(closingIssuesReferences={"nodes": [issue]})))
        self.assertEqual(code, 0)
        self.assertTrue(self.merged(runner))

    def test_a_decision_comment_on_the_pull_request_itself_counts(self) -> None:
        pull = self.pull(closingIssuesReferences={"nodes": []}, comments={"nodes": [{"body": DECISION}]})
        code, _, _, runner = self.land(self.merging(pull))
        self.assertEqual(code, 0)
        self.assertTrue(self.merged(runner))

    def test_a_merge_that_github_refuses_leaves_the_checkout_alone(self) -> None:
        runner = self.runner(merges=False)
        runner.gh.on("gh", "pr", "merge", returncode=1, stderr="Pull request is not mergeable: the base branch policy prohibits the merge.")
        runner.gh.on("gh", "pr", "view", stdout="OPEN\n")
        code, _, err, _ = self.land(runner)
        self.assertEqual(code, 2)
        self.assertIn("gh failed: Pull request is not mergeable", err)
        self.assertEqual(git(self.work, "branch", "--show-current"), BRANCH)
        self.assertEqual(git(self.origin, "rev-parse", BRANCH), self.head)

    def test_a_merge_that_is_done_although_gh_fails_still_syncs(self) -> None:
        runner = self.runner()
        runner.gh.on("gh", "pr", "merge", returncode=1, stderr="failed to delete remote branch").on("gh", "pr", "view", stdout="MERGED\n")
        code, out, err, _ = self.land(runner)
        self.assertEqual(code, 0)
        self.assertIn("Note: gh reported a problem after the merge: gh failed: failed to delete remote branch\n", err)
        self.assertEqual(git(self.work, "branch", "--show-current"), "main")
        self.assertEqual(self.branches(self.work), ["main"])

    def test_a_local_base_branch_with_commits_of_its_own_is_refused(self) -> None:
        git(self.work, "switch", "-q", "main")
        commit(self.work, {"local.txt": "only here\n"}, "wip: not pushed")
        git(self.work, "switch", "-q", BRANCH)
        self.assert_refused("the local branch main has 1 commit that origin/main lacks, so it cannot be fast-forwarded after the merge.")

    def test_a_base_branch_that_another_worktree_holds_is_refused(self) -> None:
        git(self.work, "worktree", "add", "-q", str(self.folder / "base-tree"), "main")
        self.assert_refused(f"the base branch main is checked out in the worktree {self.folder / 'base-tree'}, so this checkout cannot switch to it after the merge.")

    def test_a_clone_without_the_base_branch_is_an_environment_error(self) -> None:
        git(self.work, "config", "remote.origin.fetch", f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}")
        git(self.work, "update-ref", "-d", "refs/remotes/origin/main")
        code, out, err, runner = self.land()
        self.assertEqual((code, out), (2, ""))
        self.assertIn("This clone has no origin/main, so the gate of the base branch cannot be read.", err)
        self.assertFalse(self.merged(runner))

    def test_a_gh_merge_that_ends_well_and_merges_nothing_is_not_trusted(self) -> None:
        runner = self.runner(merges=False)
        runner.gh.on("gh", "pr", "merge").on("gh", "pr", "view", stdout="OPEN\n")
        code, out, err, _ = self.land(runner)
        self.assertEqual(code, 2)
        self.assertIn("gh pr merge ended without an error, but PR #326 is open, not merged.", err)
        self.assertNotIn("Landed", out)
        self.assertEqual(git(self.work, "branch", "--show-current"), BRANCH)
        self.assertEqual(git(self.origin, "rev-parse", BRANCH), self.head)

    def test_six_closing_issues_are_all_read(self) -> None:
        silent = {"comments": {"nodes": []}, "parent": None}
        last = {"comments": {"nodes": [{"body": DECISION}]}, "parent": None}
        code, _, _, _ = self.land(self.merging(self.pull(closingIssuesReferences={"nodes": [silent] * 5 + [last]})))
        self.assertEqual(code, 0)
        self.assertIn("closingIssuesReferences(first: 50)", LAND_QUERY)

    def test_a_failure_after_the_merge_says_that_the_pull_request_is_merged(self) -> None:
        def diverge_local_main() -> None:
            mine = git(self.work, "commit-tree", "refs/heads/main^{tree}", "-p", "refs/heads/main", "-m", "wip: made during the checks")
            git(self.work, "update-ref", "refs/heads/main", mine)

        code, _, err, _ = self.land(self.merging(on_merge=diverge_local_main))
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("PR #326 is merged, but the checkout is not synced: `git -C"), err)
        self.assertIn(BRANCH, self.branches(self.work))

    def test_a_branch_that_moved_after_the_merge_stays(self) -> None:
        code, out, _, _ = self.land(self.merging(on_merge=lambda: commit(self.work, {"late.txt": "after the merge\n"}, "fix: one more thing")))
        self.assertEqual(code, 0)
        self.assertIn(f"Kept the local branch {BRANCH}: it moved after the merge.\n", out)
        self.assertEqual(git(self.work, "log", "-1", "--format=%s", BRANCH), "fix: one more thing")


class LinkedWorktreeTest(LandCase):
    def setUp(self) -> None:
        super().setUp()
        self.tree = self.folder / "tree"
        git(self.work, "switch", "-q", "main")
        git(self.work, "worktree", "add", "-q", str(self.tree), BRANCH)
        os.chdir(self.tree)

    def test_the_worktree_and_the_branch_go_and_the_main_checkout_moves(self) -> None:
        (self.tree / "ignored.env").write_text("KEY=1\n")
        code, out, err, _ = self.land()
        self.assertEqual((code, err), (0, ""))
        merge = git(self.origin, "rev-parse", "main")
        self.assertFalse(self.tree.exists())
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), merge)
        self.assertEqual(self.branches(self.work, "--all"), ["main", "origin", "origin/main"])
        self.assertTrue(out.endswith(
            f"The main checkout {self.work} is on main at {merge[:7]}.\n"
            f"Removed the worktree {self.tree}. Run `cd {self.work}`.\n"
            "Git-ignored paths that went with it: ignored.env.\n"
            f"Deleted the local branch {BRANCH}.\n"
        ))

    def test_a_main_checkout_on_another_branch_is_not_moved(self) -> None:
        git(self.work, "switch", "-q", "-c", "feat/other")
        before = git(self.work, "rev-parse", "HEAD")
        code, out, _, _ = self.land()
        self.assertEqual(code, 0)
        self.assertIn(f"The main checkout {self.work} is on feat/other, so it was not moved. origin/main has the merge.\n", out)
        self.assertEqual((git(self.work, "branch", "--show-current"), git(self.work, "rev-parse", "HEAD")), ("feat/other", before))
        self.assertEqual(git(self.work, "rev-parse", "origin/main"), git(self.origin, "rev-parse", "main"))
        self.assertFalse(self.tree.exists())

    def test_a_worktree_whose_head_moved_after_the_merge_stays(self) -> None:
        code, out, _, _ = self.land(self.merging(on_merge=lambda: git(self.tree, "commit", "-q", "--allow-empty", "-m", "fix: one more thing")))
        self.assertEqual(code, 0)
        self.assertIn(f"Kept the worktree {self.tree} and the branch {BRANCH}: its HEAD moved after the merge.", out)
        self.assertEqual(git(self.tree, "log", "-1", "--format=%s"), "fix: one more thing")

    def test_a_git_config_that_hides_untracked_files_does_not_hide_them_from_land(self) -> None:
        git(self.work, "config", "status.showUntrackedFiles", "no")
        (self.tree / "notes.md").write_text("not committed\n")
        code, out, _, _ = self.land()
        self.assertEqual(code, 0)
        self.assertIn("it has changed or untracked files (notes.md)", out)
        self.assertTrue((self.tree / "notes.md").exists())

    def test_a_worktree_with_an_untracked_file_stays(self) -> None:
        (self.tree / "notes.md").write_text("not committed\n")
        code, out, _, _ = self.land()
        self.assertEqual(code, 0)
        self.assertIn(f"Kept the worktree {self.tree} and the branch {BRANCH}: it has changed or untracked files (notes.md).", out)
        self.assertEqual((self.tree / "notes.md").read_text(), "not committed\n")
        self.assertIn(BRANCH, self.branches(self.work))


class SubmoduleWorktreeTest(LandCase):
    def setUp(self) -> None:
        super().setUp()
        lib = self.folder / "lib"
        git(self.folder, "init", "-q", "-b", "main", str(lib))
        commit(lib, {"lib.txt": "x\n"}, "first")
        git(self.work, "submodule", "add", "-q", str(lib), "lib")
        self.head = commit(self.work, {}, "feat: add the lib submodule")
        git(self.work, "push", "-q", "origin", BRANCH)
        git(self.work, "switch", "-q", "main")
        git(self.work, "submodule", "deinit", "-q", "-f", "--all")
        self.tree = self.folder / "tree"
        git(self.work, "worktree", "add", "-q", str(self.tree), BRANCH)
        git(self.tree, "submodule", "update", "-q", "--init")
        os.chdir(self.tree)

    def test_a_worktree_with_a_clean_submodule_is_removed(self) -> None:
        code, out, _, _ = self.land()
        self.assertEqual(code, 0)
        self.assertFalse(self.tree.exists())

    def kept_for_the_submodule(self) -> None:
        code, out, _, _ = self.land()
        self.assertEqual(code, 0)
        self.assertIn(f"Kept the worktree {self.tree} and the branch {BRANCH}: a submodule in it holds a commit, a branch or a stash that no remote has (", out)
        self.assertTrue((self.tree / "lib" / "lib.txt").exists())

    def test_a_submodule_branch_that_was_never_pushed_keeps_the_worktree(self) -> None:
        lib = self.tree / "lib"
        pinned = git(lib, "rev-parse", "HEAD")
        git(lib, "switch", "-q", "-c", "side")
        commit(lib, {"side.txt": "only here\n"}, "wip: side work")
        git(lib, "switch", "-q", "--detach", pinned)
        self.assertEqual(git(self.tree, "status", "--porcelain"), "")
        self.kept_for_the_submodule()

    def test_a_stash_inside_a_submodule_keeps_the_worktree(self) -> None:
        lib = self.tree / "lib"
        (lib / "lib.txt").write_text("changed\n")
        git(lib, "stash", "-q")
        self.assertEqual(git(self.tree, "status", "--porcelain"), "")
        self.kept_for_the_submodule()

    def test_a_git_config_that_hides_submodule_changes_does_not_hide_them_from_land(self) -> None:
        git(self.tree, "config", "submodule.lib.ignore", "dirty")
        (self.tree / "lib" / "untracked-in-submodule.txt").write_text("not committed\n")
        code, out, _, _ = self.land()
        self.assertEqual(code, 0)
        self.assertIn("it has changed or untracked files (lib)", out)
        self.assertTrue((self.tree / "lib" / "untracked-in-submodule.txt").exists())

    def test_a_changed_file_inside_a_submodule_is_refused_whatever_the_config_hides(self) -> None:
        git(self.tree, "config", "submodule.lib.ignore", "dirty")
        (self.tree / "lib" / "lib.txt").write_text("changed\n")
        code, _, err, runner = self.land()
        self.assertEqual(code, 1)
        self.assertIn("- the working tree has changes.", err)
        self.assertFalse(self.merged(runner))

    def test_an_untracked_file_inside_a_submodule_keeps_the_worktree(self) -> None:
        (self.tree / "lib" / "untracked-in-submodule.txt").write_text("not committed\n")
        code, out, _, _ = self.land()
        self.assertEqual(code, 0)
        self.assertIn(f"Kept the worktree {self.tree} and the branch {BRANCH}: it has changed or untracked files (lib).", out)
        self.assertEqual((self.tree / "lib" / "untracked-in-submodule.txt").read_text(), "not committed\n")


class TwoChecksTest(LandCase):
    def base_files(self) -> dict[str, str]:
        return {GATE: workflow(self.check("first-ran", 3) + self.check("check-ran"))}

    def test_a_failing_first_check_stops_the_second_and_the_merge(self) -> None:
        code, out, err, runner = self.land()
        self.assertEqual(code, 1)
        self.assertIn("exit 3 after ", out)
        self.assertEqual(err.splitlines()[0], "Not landed: PR #326")
        self.assertIn(f"exited 3 on {BRANCH}.", err)
        self.assertTrue((self.folder / "first-ran").exists())
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.merged(runner))
        self.assertEqual(git(self.work, "branch", "--show-current"), BRANCH)


class LastCheckFailsTest(LandCase):
    def base_files(self) -> dict[str, str]:
        return {GATE: workflow(self.check("first-ran") + self.check("check-ran", 1))}

    def test_a_failing_last_check_stops_the_merge(self) -> None:
        code, _, _, runner = self.land()
        self.assertEqual(code, 1)
        self.assertTrue(self.marker.exists())
        self.assertFalse(self.merged(runner))


class CheckMovesHeadTest(LandCase):
    def base_files(self) -> dict[str, str]:
        return {GATE: workflow("- `git commit -q --allow-empty -m moved`\n")}

    def test_a_check_that_moves_head_stops_the_merge(self) -> None:
        code, _, err, runner = self.land()
        self.assertEqual(code, 1)
        self.assertIn("- the checks changed tracked files or moved HEAD.", err)
        self.assertFalse(self.merged(runner))


class CheckChangesFileTest(LandCase):
    def base_files(self) -> dict[str, str]:
        return {GATE: workflow(f"- `{sys.executable} -c \"open('app.txt', 'w').write('formatted')\"`\n")}

    def test_a_check_that_changes_a_tracked_file_stops_the_merge(self) -> None:
        code, _, err, runner = self.land()
        self.assertEqual(code, 1)
        self.assertIn("- the checks changed tracked files or moved HEAD.", err)
        self.assertFalse(self.merged(runner))


class EvidenceGateTest(LandCase):
    def base_files(self) -> dict[str, str]:
        return {GATE: workflow(self.check("check-ran")) + "\n## Evidence paths\n\nVerify command: just verify\n\n- `app.txt`\n"}

    def test_a_pull_request_without_its_image_is_refused(self) -> None:
        self.assert_refused("it changes 1 evidence path (app.txt), and its body has no `## Verification` section with an image. Make the screenshots with just verify.")

    def test_a_pull_request_with_its_image_lands(self) -> None:
        body = "Closes #227\n\n## Verification\n\n![app](https://github.com/julian-perge/urchin/blob/abc/pr-326/app.png?raw=true)\n"
        code, _, _, runner = self.land(self.merging(self.pull(body=body)))
        self.assertEqual(code, 0)
        self.assertTrue(self.merged(runner))


class NoChecksTest(LandCase):
    def base_files(self) -> dict[str, str]:
        return {GATE: "# Workflow\n\n## Review\n\nText.\n"}

    def test_a_repo_without_a_check_command_is_refused(self) -> None:
        self.assert_refused("docs/agents/workflow.md has no `## Checks` heading with a command")


class GateFromBaseTest(LandCase):
    def branch_files(self) -> dict[str, str]:
        return {GATE: workflow(self.check("weaker-check-ran"))}

    def test_a_pull_request_cannot_swap_the_checks_it_is_judged_by(self) -> None:
        files = {"totalCount": 2, "nodes": [{"path": "app.txt"}, {"path": GATE}]}
        code, _, err, _ = self.land(self.merging(self.pull(files=files)))
        self.assertEqual(code, 0)
        self.assertEqual(err, f"Note: this pull request changes {GATE}. The gate comes from main.\n")
        self.assertTrue(self.marker.exists())
        self.assertFalse((self.folder / "weaker-check-ran").exists())


class NoGateOnBaseTest(LandCase):
    def base_files(self) -> dict[str, str]:
        return {}

    def branch_files(self) -> dict[str, str]:
        return {GATE: workflow(self.check("check-ran"))}

    def test_the_first_pull_request_of_a_repo_is_judged_by_its_own_file(self) -> None:
        code, _, err, _ = self.land()
        self.assertEqual(code, 0)
        self.assertEqual(err, f"Note: main has no {GATE} yet, so the gate comes from this checkout.\n")
        self.assertTrue(self.marker.exists())


class UnreadableGateTest(LandCase):
    def base_files(self) -> dict[str, str]:
        return {GATE: workflow("- `just gut` and then `just pytest`\n- `sh -c 'open quote`\n")}

    def test_a_list_item_that_cannot_be_read_stops_before_anything_runs(self) -> None:
        code, out, err, runner = self.land()
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(len(err.splitlines()), 3)
        self.assertIn("is not one command in backticks with nothing after it.", err)
        self.assertIn("does not parse as a command (No closing quotation).", err)
        self.assertFalse(self.merged(runner))


if __name__ == "__main__":
    unittest.main()
