import unittest

from agent_skills.tracker import Groups, IssueRow, OpenPull, TaskMatch, TrackerIssue, group, next_step, plan_candidates

SPECS = frozenset({"spec/35-draynor-region-import.md", "spec/107-hub.md", "spec/107-store.md"})


def ready(number: int, **fields: object) -> TrackerIssue:
    return TrackerIssue(number, f"Task {number}", labels=("ready-for-agent",), **fields)  # type: ignore[arg-type]


class ReviewGroupTest(unittest.TestCase):
    def test_every_open_pr_that_is_not_a_draft_is_a_review_row(self) -> None:
        pulls = [OpenPull(60, "Region scenery", "feat/49-region-scenery", "Closes #49", created_at="2026-11-12T00:00:00Z"), OpenPull(61, "Draft", draft=True)]
        rows = group(pulls, [], SPECS, {}).review
        self.assertEqual([row.pr for row in rows], [60])
        self.assertEqual(rows[0].task, TaskMatch(49, "body"))

    def test_task_from_the_branch_name_is_a_guess(self) -> None:
        rows = group([OpenPull(27, "Fixes", "docs/22-runbook-acceptance-fixes")], [], SPECS, {}).review
        self.assertEqual(rows[0].task, TaskMatch(22, "branch name", guess=True))

    def test_spec_of_the_task_uses_the_open_issue_body(self) -> None:
        issues = [TrackerIssue(51, "Compare", body="Spec: spec/35-draynor-region-import.md", parent_number=35)]
        rows = group([OpenPull(70, "Compare", "feat/51-compare", "Closes #51")], issues, SPECS, {}).review
        self.assertEqual(rows[0].spec.path, "spec/35-draynor-region-import.md")
        self.assertEqual(rows[0].spec.source, "issue body")

    def test_oldest_pr_comes_first(self) -> None:
        pulls = [OpenPull(80, "New", created_at="2026-11-14T00:00:00Z"), OpenPull(70, "Old", created_at="2026-11-10T00:00:00Z")]
        self.assertEqual([row.pr for row in group(pulls, [], SPECS, {}).review], [70, 80])


class BuildGroupTest(unittest.TestCase):
    def test_ready_unassigned_unblocked_and_no_open_pr(self) -> None:
        self.assertEqual([row.number for row in group([], [ready(31)], SPECS, {}).build], [31])

    def test_label_assignee_blocker_and_open_pr_each_keep_an_issue_out(self) -> None:
        issues = [
            TrackerIssue(10, "No label"),
            ready(11, assigned=True),
            ready(12, open_blockers=1),
            ready(13, open_pull_requests=(60,)),
        ]
        self.assertEqual(group([], issues, SPECS, {}).build, ())

    def test_frontier_rows_come_first_then_by_number(self) -> None:
        issues = [ready(216, parent_number=107), ready(204, parent_number=107), ready(174, parent_number=158), ready(191, parent_number=158)]
        rows = group([], issues, SPECS, {}).build
        self.assertEqual([(row.number, row.frontier) for row in rows], [(174, True), (204, True), (191, False), (216, False)])

    def test_a_lower_sibling_without_ready_for_agent_does_not_take_the_mark(self) -> None:
        issues = [TrackerIssue(5, "Live run", labels=("ready-for-human",), parent_number=1), ready(11, parent_number=1), ready(13, parent_number=1)]
        rows = group([], issues, SPECS, {}).build
        self.assertEqual([(row.number, row.frontier) for row in rows], [(11, True), (13, False)])

    def test_a_frontier_with_an_open_pr_marks_no_other_row(self) -> None:
        issues = [ready(11, parent_number=1, open_pull_requests=(60,)), ready(13, parent_number=1)]
        self.assertEqual([(row.number, row.frontier) for row in group([], issues, SPECS, {}).build], [(13, False)])

    def test_a_task_with_no_parent_is_its_own_frontier(self) -> None:
        rows = group([], [ready(188), ready(186), ready(11, parent_number=1)], SPECS, {}).build
        self.assertTrue(all(row.frontier for row in rows))


class PlanGroupTest(unittest.TestCase):
    def test_spec_file_of_an_open_issue_that_no_sub_issue_names(self) -> None:
        issues = [TrackerIssue(107, "UI overhaul", labels=("ready-for-human",), sub_issue_total=2)]
        rows = group([], issues, SPECS, {107: ("Spec: `spec/107-hub.md`", "Closed task body")}).plan
        self.assertEqual(rows, (IssueRow(107, "UI overhaul", spec="spec/107-store.md"),))

    def test_one_spec_per_issue_and_no_sub_issues(self) -> None:
        rows = group([], [TrackerIssue(35, "Import a map chunk", labels=("needs-triage",))], SPECS, {}).plan
        self.assertEqual(rows, (IssueRow(35, "Import a map chunk", spec="spec/35-draynor-region-import.md"),))

    def test_a_spec_file_of_a_closed_issue_gives_no_row(self) -> None:
        self.assertEqual(group([], [TrackerIssue(36, "Placements", parent_number=35)], SPECS, {}).plan, ())

    def test_candidates_are_open_issues_with_spec_files_outside_review_and_build(self) -> None:
        issues = [TrackerIssue(35, "Import"), ready(107), TrackerIssue(9, "No spec")]
        self.assertEqual(plan_candidates([], issues, SPECS), [35])
        self.assertEqual(plan_candidates([OpenPull(70, "x", "feat/35-import")], issues, SPECS), [])


class SpecGroupTest(unittest.TestCase):
    def test_no_parent_no_sub_issues_no_spec_and_no_listed_label(self) -> None:
        rows = group([], [TrackerIssue(69, "Loc shadow", labels=("bug",))], SPECS, {}).spec
        self.assertEqual(rows, (IssueRow(69, "Loc shadow"),))

    def test_each_condition_keeps_an_issue_out(self) -> None:
        issues = [
            TrackerIssue(70, "Has a parent", parent_number=1),
            TrackerIssue(71, "Has sub-issues", sub_issue_total=2),
            TrackerIssue(72, "Has a spec", body="Spec: spec/107-hub.md"),
            TrackerIssue(73, "Human", labels=("ready-for-human",)),
            TrackerIssue(74, "Needs info", labels=("needs-info",)),
            TrackerIssue(75, "Wontfix", labels=("wontfix",)),
        ]
        self.assertEqual(group([], issues, SPECS, {}).spec, ())


class IdeaGroupTest(unittest.TestCase):
    def test_needs_triage_issues(self) -> None:
        rows = group([], [TrackerIssue(13, "Rigs", labels=("needs-triage",)), TrackerIssue(67, "Shared materials", labels=("needs-triage",), parent_number=35)], SPECS, {}).idea
        self.assertEqual([row.number for row in rows], [13, 67])


class PriorityTest(unittest.TestCase):
    def test_build_wins_over_idea(self) -> None:
        groups = group([], [TrackerIssue(30, "Fade", labels=("ready-for-agent", "needs-triage"))], SPECS, {})
        self.assertEqual(([r.number for r in groups.build], groups.idea), ([30], ()))

    def test_build_wins_over_plan(self) -> None:
        groups = group([], [ready(35)], SPECS, {})
        self.assertEqual(([r.number for r in groups.build], groups.plan), ([35], ()))

    def test_plan_wins_over_idea(self) -> None:
        groups = group([], [TrackerIssue(35, "Import", labels=("needs-triage",))], SPECS, {})
        self.assertEqual(([r.number for r in groups.plan], groups.idea), ([35], ()))

    def test_spec_wins_over_idea_is_impossible_because_needs_triage_keeps_an_issue_out_of_spec(self) -> None:
        groups = group([], [TrackerIssue(13, "Rigs", labels=("needs-triage",))], SPECS, {})
        self.assertEqual((groups.spec, [r.number for r in groups.idea]), ((), [13]))

    def test_the_task_of_a_review_row_joins_no_other_group(self) -> None:
        groups = group([OpenPull(70, "Import", "feat/31-decode-errors")], [ready(31)], SPECS, {})
        self.assertEqual(([r.pr for r in groups.review], groups.build), ([70], ()))


class NextStepTest(unittest.TestCase):
    def test_oldest_pr_first(self) -> None:
        groups = group([OpenPull(80, "New", created_at="2"), OpenPull(70, "Old", created_at="1")], [ready(31)], SPECS, {})
        self.assertEqual(next_step(groups).pr, 70)  # type: ignore[union-attr]

    def test_lowest_frontier_task_when_review_is_empty(self) -> None:
        groups = group([], [ready(204, parent_number=107), ready(174, parent_number=158), ready(191, parent_number=158)], SPECS, {})
        self.assertEqual(next_step(groups), IssueRow(174, "Task 174", frontier=True))

    def test_nothing_when_review_and_build_are_empty(self) -> None:
        self.assertIsNone(next_step(Groups()))


if __name__ == "__main__":
    unittest.main()
