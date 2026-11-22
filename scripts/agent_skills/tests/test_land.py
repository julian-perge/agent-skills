import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from agent_skills import cli, land
from agent_skills.github import parse_worktrees
from fakes import FakeRunner, fixture_text, names_repo

URCHIN = "julian-perge/urchin"
HEAD = "6baf62c2ba12fbdb9f53609af6710f6bcfa45b55"
BRANCH = "fix/227-inventory-doll"
DECISION = "### Decisions from the review of PR #326\n\n- No findings."
OPEN = land.LandPull(326, "Place the doll", base="main", head=BRANCH, head_commit=HEAD, comments=(DECISION,))
NO_EVIDENCE = land.Evidence(configured=False)


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
        self.assertEqual(reasons, ["no review decision comment names PR #326. The review posts it with `agent-skills decide <issue> --from review --pr 326`."])

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


def pull_json(**changes: object) -> str:
    data = json.loads(fixture_text("land-urchin-326.json"))
    pull = {"state": "OPEN", "mergeable": "MERGEABLE", "headRefName": BRANCH, "headRefOid": HEAD, **changes}
    data["data"]["repository"]["pullRequest"].update(pull)
    return json.dumps(data)


class LandVerbTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve() / "urchin"
        (self.root / "docs" / "agents").mkdir(parents=True)
        self.marker = self.root.parent / "check-ran"
        self.write_checks(0)
        patcher = mock.patch.dict(os.environ, {"TMPDIR": str(self.root.parent)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_checks(self, code: int) -> None:
        script = f"import pathlib, sys; pathlib.Path({str(self.marker)!r}).write_text('x'); sys.exit({code})"
        (self.root / "docs" / "agents" / "workflow.md").write_text(f'# Workflow\n\n## Checks\n\n- `{sys.executable} -c "{script}"`\n')

    def top(self, runner: FakeRunner) -> FakeRunner:
        return runner.on("git", "rev-parse", "--show-toplevel", stdout=f"{self.root}\n")

    def gate(self, pull: str, branch: str = BRANCH, behind: int = 0) -> FakeRunner:
        """The calls up to the checks, in the order that `land` makes them."""
        runner = self.top(FakeRunner()).on("gh", "api", "graphql", stdout=pull)
        runner.on("git", "rev-parse", "--abbrev-ref", "HEAD", stdout=f"{branch}\n").on("git", "rev-parse", "HEAD", stdout=f"{HEAD}\n")
        runner.on("git", "status", "--porcelain").on("git", "fetch", "origin", "main").on("git", "rev-list", "--count", stdout=f"{behind}\n")
        return runner

    def checked(self, pull: str) -> FakeRunner:
        """The calls up to the merge: the gate, one check run, and the second look at the checkout."""
        runner = self.top(self.gate(pull))
        return runner.on("git", "status", "--porcelain").on("git", "rev-parse", "HEAD", stdout=f"{HEAD}\n").on("gh", "pr", "merge")

    def run_cli(self, runner: FakeRunner) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch("agent_skills.cli.time.sleep") as self.sleep:
            code = cli.main(["--repo", URCHIN, "land", "326"], runner)
        return code, out.getvalue(), err.getvalue()

    def writes(self, runner: FakeRunner) -> list[list[str]]:
        def is_read(call: list[str]) -> bool:
            words = call[3:] if call[:2] == ["git", "-C"] else call[1:]
            return call[:2] == ["gh", "api"] or (call[0] == "git" and (words[0] in ("rev-parse", "status", "fetch", "rev-list") or words[:2] == ["worktree", "list"]))

        return [call for call in runner.calls if not is_read(call)]

    def test_a_clean_pull_request_merges_and_the_checkout_ends_on_the_base_branch(self) -> None:
        runner = self.checked(pull_json())
        runner.on("git", "worktree", "list", stdout=f"worktree {self.root}\nHEAD {HEAD}\nbranch refs/heads/{BRANCH}\n")
        runner.on("git", "switch", "main").on("git", "pull", "--ff-only").on("git", "branch", "-D", BRANCH)
        runner.on("git", "rev-parse", "--short", "HEAD", stdout="9f8e7d6\n")
        code, out, err = self.run_cli(runner)
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(self.marker.exists())
        self.assertIn("exit 0 after ", out)
        self.assertTrue(out.endswith(
            "Landed PR #326 into main: https://github.com/julian-perge/urchin/pull/326\n"
            f"This checkout is on main at 9f8e7d6.\nDeleted the local branch {BRANCH}.\n"
        ))
        root = str(self.root)
        self.assertEqual(self.writes(runner), [
            ["gh", "pr", "merge", "326", "--repo", URCHIN, "--merge", "--delete-branch", "--match-head-commit", HEAD],
            ["git", "switch", "main"],
            ["git", "-C", root, "pull", "--ff-only", "--prune", "origin", "main"],
            ["git", "-C", root, "branch", "-D", BRANCH],
        ])
        self.assertTrue(all(names_repo(call, URCHIN) for call in runner.gh_calls()))

    def test_a_linked_worktree_is_removed_and_the_main_checkout_moves(self) -> None:
        runner = self.checked(pull_json())
        runner.on("git", "worktree", "list", stdout=f"worktree /code/urchin\nHEAD 1\nbranch refs/heads/main\n\nworktree {self.root}\nHEAD {HEAD}\nbranch refs/heads/{BRANCH}\n")
        runner.on("git", "-C", "/code/urchin", "pull", "--ff-only").on("git", "rev-parse", "--short", "HEAD", stdout="9f8e7d6\n")
        runner.on("git", "status", "--porcelain", "--untracked-files=all").on("git", "worktree", "remove").on("git", "branch", "-D", BRANCH)
        code, out, _ = self.run_cli(runner)
        self.assertEqual(code, 0)
        self.assertIn("The main checkout /code/urchin is on main at 9f8e7d6.\n", out)
        self.assertIn(f"Removed the worktree {self.root} and the local branch {BRANCH}. Run `cd /code/urchin`.\n", out)
        self.assertEqual(self.writes(runner)[1:], [
            ["git", "-C", "/code/urchin", "pull", "--ff-only", "--prune", "origin", "main"],
            ["git", "-C", "/code/urchin", "worktree", "remove", "--force", str(self.root)],
            ["git", "-C", "/code/urchin", "branch", "-D", BRANCH],
        ])

    def test_a_linked_worktree_with_untracked_files_stays(self) -> None:
        runner = self.checked(pull_json())
        runner.on("git", "worktree", "list", stdout=f"worktree /code/urchin\nHEAD 1\nbranch refs/heads/feat/other\n\nworktree {self.root}\nHEAD {HEAD}\nbranch refs/heads/{BRANCH}\n")
        runner.on("git", "-C", "/code/urchin", "fetch", "--prune").on("git", "status", "--porcelain", "--untracked-files=all", stdout="?? notes.md\n?? shots/a.png\n")
        code, out, _ = self.run_cli(runner)
        self.assertEqual(code, 0)
        self.assertIn("The main checkout /code/urchin is on feat/other, so it was not moved. origin/main has the merge.\n", out)
        self.assertIn("the worktree has untracked files (notes.md and 1 more)", out)
        self.assertEqual(len(self.writes(runner)), 1)

    def test_a_failing_check_merges_nothing(self) -> None:
        self.write_checks(3)
        runner = self.top(self.gate(pull_json()))
        code, out, err = self.run_cli(runner)
        self.assertEqual(code, 1)
        self.assertIn("exit 3 after ", out)
        self.assertIn(f"Not landed: PR #326\n- the check `{sys.executable} -c", err)
        self.assertIn(f"exited 3 on {BRANCH}.", err)
        self.assertEqual(self.writes(runner), [])

    def test_merge_conflicts_stop_before_the_checks(self) -> None:
        runner = self.gate(pull_json(mergeable="CONFLICTING"), behind=3)
        code, out, err = self.run_cli(runner)
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err.splitlines()[0], "Not landed: PR #326")
        self.assertIn("- the pull request has merge conflicts with main.", err)
        self.assertIn("- the PR branch is 3 commits behind main", err)
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.writes(runner), [])

    def test_no_review_decision_comment_stops_before_the_checks(self) -> None:
        issue = {"comments": {"nodes": [{"body": "### Decisions from the build of #227\n\n- a"}]}, "parent": None}
        runner = self.gate(pull_json(closingIssuesReferences={"nodes": [issue]}))
        code, _, err = self.run_cli(runner)
        self.assertEqual(code, 1)
        self.assertIn("- no review decision comment names PR #326.", err)
        self.assertFalse(self.marker.exists())

    def test_a_decision_comment_on_the_parent_issue_counts(self) -> None:
        issue = {"comments": {"nodes": []}, "parent": {"comments": {"nodes": [{"body": DECISION}]}}}
        runner = self.top(self.gate(pull_json(closingIssuesReferences={"nodes": [issue]})))
        runner.on("git", "status", "--porcelain", stdout=" M scenes/a.tscn\n")
        code, _, err = self.run_cli(runner)
        self.assertEqual(code, 1)
        self.assertIn("the checks changed tracked files or moved HEAD", err)
        self.assertEqual(self.writes(runner), [])

    def test_an_unknown_merge_state_is_read_again(self) -> None:
        runner = self.top(FakeRunner()).on("gh", "api", "graphql", stdout=pull_json(mergeable="UNKNOWN"))
        runner.on("gh", "api", "graphql", stdout=pull_json(mergeable="CONFLICTING"))
        runner.on("git", "rev-parse", "--abbrev-ref", "HEAD", stdout=f"{BRANCH}\n").on("git", "rev-parse", "HEAD", stdout=f"{HEAD}\n")
        runner.on("git", "status", "--porcelain").on("git", "fetch", "origin", "main").on("git", "rev-list", "--count", stdout="0\n")
        code, _, err = self.run_cli(runner)
        self.assertEqual(code, 1)
        self.assertEqual(err, "Not landed: PR #326\n- the pull request has merge conflicts with main.\n")
        self.sleep.assert_called_once_with(2)

    def test_a_merge_that_github_refuses_leaves_the_checkout_alone(self) -> None:
        runner = self.top(self.gate(pull_json()))
        runner.on("git", "status", "--porcelain").on("git", "rev-parse", "HEAD", stdout=f"{HEAD}\n")
        runner.on("gh", "pr", "merge", returncode=1, stderr="Pull request is not mergeable: the base branch policy prohibits the merge.")
        code, _, err = self.run_cli(runner)
        self.assertEqual(code, 2)
        self.assertIn("gh failed: Pull request is not mergeable", err)
        self.assertEqual(len(self.writes(runner)), 1)

    def test_a_failure_after_the_merge_says_that_the_pull_request_is_merged(self) -> None:
        runner = self.checked(pull_json())
        runner.on("git", "worktree", "list", stdout=f"worktree {self.root}\nHEAD {HEAD}\nbranch refs/heads/{BRANCH}\n")
        runner.on("git", "switch", "main", returncode=1, stderr="fatal: 'main' is already used by worktree at '/code/other'")
        code, _, err = self.run_cli(runner)
        self.assertEqual(code, 2)
        self.assertIn("PR #326 is merged, but the checkout is not synced: `git switch main` failed", err)


if __name__ == "__main__":
    unittest.main()
