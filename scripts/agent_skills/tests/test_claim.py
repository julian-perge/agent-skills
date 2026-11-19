import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from agent_skills import cli
from agent_skills.tracker import Issue, Link, branch_type, claim_refusal, slug, task_refs
from fakes import FakeRunner, fixture_json, names_repo

BLENDER = "julian-perge/blender-addon-rs317-667mqo-makeup"
BRANCH_31 = "feat/31-the-appearance-panel-says-nothing"


def is_write(call: list[str]) -> bool:
    return call[:3] == ["gh", "issue", "edit"] or call[:2] in (["git", "fetch"], ["git", "switch"])


class SlugTest(unittest.TestCase):
    def test_lowercase_words_joined_with_dashes(self) -> None:
        self.assertEqual(slug("Region scenery"), "region-scenery")

    def test_at_most_five_words(self) -> None:
        self.assertEqual(slug("The appearance panel says nothing when a cache definition fails"), "the-appearance-panel-says-nothing")

    def test_apostrophes_and_punctuation_go(self) -> None:
        self.assertEqual(slug("A held item's fade property can't follow"), "a-held-items-fade-property")

    def test_whole_words_are_dropped_to_fit_40_characters(self) -> None:
        self.assertEqual(slug("Internationalization configuration documentation improvements everywhere"), "internationalization-configuration")

    def test_one_word_longer_than_40_characters_is_cut(self) -> None:
        self.assertEqual(slug("a" * 50), "a" * 40)


class BranchTypeTest(unittest.TestCase):
    def test_type_flag_wins(self) -> None:
        self.assertEqual(branch_type(("bug",), "docs"), "docs")

    def test_bug_label_gives_fix(self) -> None:
        self.assertEqual(branch_type(("bug", "needs-triage"), None), "fix")

    def test_other_labels_give_feat(self) -> None:
        self.assertEqual(branch_type(("enhancement",), None), "feat")


class ClaimRefusalTest(unittest.TestCase):
    def test_closed(self) -> None:
        self.assertEqual(claim_refusal(Issue(49, "x", state="CLOSED"), "julian-perge"), "#49 is closed.")

    def test_assigned_to_someone_else(self) -> None:
        self.assertEqual(claim_refusal(Issue(31, "x", assignees=("someone-else",)), "julian-perge"), "#31 is assigned to @someone-else.")

    def test_open_blocker(self) -> None:
        issue = Issue(215, "x", blockers=(Link(214, "CLOSED"), Link(209, "OPEN")))
        self.assertEqual(claim_refusal(issue, "julian-perge"), "#215 has open blockers: #209.")

    def test_assigned_to_me_and_closed_blockers_are_fine(self) -> None:
        self.assertIsNone(claim_refusal(Issue(273, "x", assignees=("julian-perge",), blockers=(Link(271, "CLOSED"),)), "julian-perge"))

    def test_open_blocker_with_a_commit_on_the_branch_is_fine(self) -> None:
        issue = Issue(215, "x", blockers=(Link(209, "OPEN"),))
        self.assertIsNone(claim_refusal(issue, "julian-perge", frozenset({209})))

    def test_open_blocker_without_a_commit_on_the_branch_is_refused(self) -> None:
        issue = Issue(215, "x", blockers=(Link(208, "OPEN"), Link(209, "OPEN")))
        self.assertEqual(
            claim_refusal(issue, "julian-perge", frozenset({208})),
            "#215 has open blockers with no commit on this branch: #209.",
        )


class TaskRefsTest(unittest.TestCase):
    def test_only_a_reference_at_the_end_of_the_subject_counts(self) -> None:
        subjects = ["feat: add the panel (#209)", "docs: fix the README (#24) ", "fix: mention #210 in passing", "chore: (#7) in the middle"]
        self.assertEqual(task_refs(subjects), frozenset({209, 24}))


class ClaimVerbTest(unittest.TestCase):
    def runner_for(self, fixture: str) -> FakeRunner:
        return FakeRunner().on("gh", "api", "graphql", stdout=fixture_json(fixture))

    def with_clean_checkout(self, runner: FakeRunner, branch: str, existing: str = "", status: str = "") -> FakeRunner:
        runner.on("git", "status", "--porcelain", stdout=status)
        runner.on("git", "symbolic-ref", "refs/remotes/origin/HEAD", stdout="refs/remotes/origin/main\n")
        runner.on("git", "for-each-ref", f"refs/heads/{branch}", stdout=existing)
        return runner

    def with_writes(self, runner: FakeRunner, number: int, branch: str) -> FakeRunner:
        runner.on("gh", "issue", "edit", str(number))
        runner.on("git", "fetch", "origin", "main")
        runner.on("git", "switch", "-c", branch, "origin/main")
        runner.on("git", "rev-parse", "--short", "HEAD", stdout="1a2b3c4\n")
        return runner

    def claim(self, runner: FakeRunner, argv: list[str], repo: str = BLENDER) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--repo", repo, "claim", *argv], runner)
        return code, out.getvalue(), err.getvalue()

    def test_success_assigns_and_branches_from_the_default_branch(self) -> None:
        runner = self.with_writes(self.with_clean_checkout(self.runner_for("claim-blender-31.json"), BRANCH_31), 31, BRANCH_31)
        code, out, _ = self.claim(runner, ["31"])
        self.assertEqual(code, 0)
        self.assertEqual(out, f"Claimed #31 for @me. Branch {BRANCH_31} from origin/main at 1a2b3c4.\n")
        self.assertEqual(
            [call for call in runner.calls if is_write(call)],
            [
                ["gh", "issue", "edit", "31", "--repo", BLENDER, "--add-assignee", "@me"],
                ["git", "fetch", "origin", "main"],
                ["git", "switch", "-c", BRANCH_31, "origin/main"],
            ],
        )
        self.assertTrue(all(names_repo(call, BLENDER) for call in runner.gh_calls()))

    def test_bug_label_and_type_flag_name_the_branch(self) -> None:
        branch = "fix/30-a-held-items-fade-property"
        runner = self.with_writes(self.with_clean_checkout(self.runner_for("claim-blender-30-bug.json"), branch), 30, branch)
        code, out, _ = self.claim(runner, ["30"])
        self.assertEqual(code, 0)
        self.assertIn(f"Branch {branch} ", out)
        branch = "docs/30-a-held-items-fade-property"
        runner = self.with_writes(self.with_clean_checkout(self.runner_for("claim-blender-30-bug.json"), branch), 30, branch)
        self.assertEqual(self.claim(runner, ["30", "--type", "docs"])[0], 0)

    def test_no_branch_only_assigns(self) -> None:
        runner = self.runner_for("claim-blender-31.json").on("gh", "issue", "edit", "31")
        code, out, _ = self.claim(runner, ["31", "--no-branch"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "Claimed #31 for @me.\n")
        self.assertEqual(runner.git_calls(), [])

    def test_no_assign_only_branches(self) -> None:
        runner = self.with_clean_checkout(self.runner_for("claim-blender-31.json"), BRANCH_31)
        runner.on("git", "fetch", "origin", "main").on("git", "switch", "-c", BRANCH_31).on("git", "rev-parse", "--short", "HEAD", stdout="1a2b3c4\n")
        code, out, _ = self.claim(runner, ["31", "--no-assign"])
        self.assertEqual(code, 0)
        self.assertEqual(out, f"Branch {BRANCH_31} from origin/main at 1a2b3c4.\n")
        self.assertFalse(any(call[:3] == ["gh", "issue", "edit"] for call in runner.calls))

    def test_already_mine_skips_the_assign_call(self) -> None:
        runner = self.runner_for("claim-urchin-273-mine.json")
        code, out, _ = self.claim(runner, ["273", "--no-branch"], "julian-perge/urchin")
        self.assertEqual(code, 0)
        self.assertEqual(out, "#273 is already assigned to @me.\n")
        self.assertEqual(len(runner.calls), 1)

    def assert_refused(self, runner: FakeRunner, argv: list[str], reason: str, repo: str = BLENDER) -> None:
        code, out, err = self.claim(runner, argv, repo)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err, f"Not claimed: {reason}\n")
        self.assertEqual([call for call in runner.calls if is_write(call)], [])

    def test_closed_issue_is_refused(self) -> None:
        self.assert_refused(self.runner_for("claim-blender-49-closed.json"), ["49"], "#49 is closed.")

    def test_issue_assigned_to_someone_else_is_refused(self) -> None:
        self.assert_refused(self.runner_for("claim-blender-31-assigned.json"), ["31"], "#31 is assigned to @someone-else.")

    def test_blocked_issue_is_refused(self) -> None:
        self.assert_refused(self.runner_for("claim-urchin-215-blocked.json"), ["215"], "#215 has open blockers: #209.", "julian-perge/urchin")

    def test_dirty_tree_is_refused(self) -> None:
        runner = self.with_clean_checkout(self.runner_for("claim-blender-31.json"), BRANCH_31, status=" M addon/panel.py\n")
        self.assert_refused(runner, ["31"], "the working tree has changes. Commit or stash them, or pass --no-branch.")

    def test_existing_branch_is_refused(self) -> None:
        runner = self.with_clean_checkout(self.runner_for("claim-blender-31.json"), BRANCH_31, existing=f"refs/heads/{BRANCH_31}\n")
        self.assert_refused(runner, ["31"], f"the branch {BRANCH_31} already exists.")

    def with_branch_subjects(self, runner: FakeRunner, subjects: str) -> FakeRunner:
        runner.on("git", "symbolic-ref", "refs/remotes/origin/HEAD", stdout="refs/remotes/origin/main\n")
        runner.on("git", "log", "--format=%s", "origin/main..HEAD", stdout=subjects)
        return runner

    def test_auto_claims_a_task_whose_blocker_has_a_commit_on_the_branch(self) -> None:
        runner = self.with_branch_subjects(self.runner_for("claim-urchin-215-blocked.json"), "feat: add the region scenery (#209)\n")
        runner.on("gh", "issue", "edit", "215")
        code, out, _ = self.claim(runner, ["215", "--auto"], "julian-perge/urchin")
        self.assertEqual(code, 0)
        self.assertEqual(out, "Claimed #215 for @me.\n")
        self.assertEqual(
            [call for call in runner.calls if is_write(call)],
            [["gh", "issue", "edit", "215", "--repo", "julian-perge/urchin", "--add-assignee", "@me"]],
        )

    def test_auto_refuses_a_task_whose_blocker_has_no_commit_on_the_branch(self) -> None:
        runner = self.with_branch_subjects(self.runner_for("claim-urchin-215-blocked.json"), "feat: add something else (#208)\n")
        self.assert_refused(runner, ["215", "--auto"], "#215 has open blockers with no commit on this branch: #209.", "julian-perge/urchin")

    def test_dirty_tree_does_not_matter_with_no_branch(self) -> None:
        runner = self.runner_for("claim-blender-31.json").on("gh", "issue", "edit", "31")
        self.assertEqual(self.claim(runner, ["31", "--no-branch"])[0], 0)


if __name__ == "__main__":
    unittest.main()
