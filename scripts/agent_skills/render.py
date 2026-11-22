from collections.abc import Sequence

from agent_skills.land import Evidence
from agent_skills.tracker import Box, Frontier, Groups, Issue, IssueRow, PullRequest, ReviewRow, SpecMatch, SubIssue, TaskMatch, is_decision

BODY_LIMIT = 2000
COMMENT_LIMIT = 600
COMMENTS_SHOWN = 3
BRIEF_BODY_LIMIT: int | None = None
BRIEF_COMMENTS_SHOWN = 1
BRIEF_COMMENT_LIMIT: int | None = None
ROWS_SHOWN = 10
NEXT_ROWS_SHOWN = 5


def cell(text: str) -> str:
    return text.replace("|", "\\|")


def assignees(logins: Sequence[str]) -> str:
    return ", ".join(f"@{login}" for login in logins) or "none"


def sub_issue_count(subs: Sequence[SubIssue]) -> str:
    if not subs:
        return "none"
    return f"{sum(1 for s in subs if s.state == 'OPEN')} open of {len(subs)}"


def frontier_report(number: int, title: str, subs: Sequence[SubIssue], result: Frontier) -> str:
    lines = [f"# #{number} {title}", "", f"Sub-issues: {sub_issue_count(subs)}", ""]
    open_subs = sorted((s for s in subs if s.state == "OPEN"), key=lambda s: s.number)
    if open_subs:
        lines += ["| # | Assignee | Open blockers | Title |", "| --- | --- | --- | --- |"]
        lines += [f"| #{s.number} | {assignees(s.assignees)} | {s.open_blockers} | {cell(s.title)} |" for s in open_subs]
        lines.append("")
    lines.append(f"Frontier: #{result.number}" if result.number is not None else f"Frontier: none ({result.reason})")
    return "\n".join(lines) + "\n"


def cut(text: str, limit: int | None) -> str:
    if limit is None or len(text) <= limit:
        return text
    return f"{text[:limit]}\n[cut: {len(text) - limit} more characters, run with --full]"


def spec_line(match: SpecMatch) -> str:
    if match.path is None:
        return f"none (candidates: {', '.join(match.candidates)})" if match.candidates else "none"
    return f"{match.path} (guess)" if match.guess else f"{match.path} (from {match.source})"


def blocker_line(issue: Issue) -> str:
    open_ones = ", ".join(f"#{b.number}" for b in issue.blockers if b.state == "OPEN") or "none"
    closed = ", ".join(f"#{b.number}" for b in issue.blockers if b.state != "OPEN")
    return f"{open_ones} (closed: {closed})" if closed else open_ones


def issue_report(issue: Issue, spec: SpecMatch, full: bool, body_limit: int | None = BODY_LIMIT, comments_shown: int = COMMENTS_SHOWN, comment_limit: int | None = COMMENT_LIMIT) -> str:
    parent = f"#{issue.parent_number} {issue.parent_title}" if issue.parent_number else "none"
    pulls = ", ".join(f"#{pr.number} {pr.state}" for pr in issue.pull_requests) or "none"
    subs = issue.sub_issues
    lines = [
        f"# #{issue.number} {issue.title} [{issue.state}]",
        f"- URL: {issue.url}",
        f"- Labels: {', '.join(issue.labels) or 'none'}",
        f"- Assignee: {assignees(issue.assignees)}",
        f"- Parent: {parent}",
        f"- Spec: {spec_line(spec)}",
        f"- Open blockers: {blocker_line(issue)}",
        f"- Pull requests: {pulls}",
        f"- Sub-issues: {issue.sub_issue_total - issue.sub_issue_completed} open of {issue.sub_issue_total}" if issue.sub_issue_total else "- Sub-issues: none",
        "",
    ]
    if subs:
        rows = sorted(subs, key=lambda s: (s.state != "OPEN", s.number))
        shown = rows if full else rows[:ROWS_SHOWN]
        lines += ["| # | State | Assignee | Open blockers | Title |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| #{s.number} | {s.state} | {assignees(s.assignees)} | {s.open_blockers} | {cell(s.title)} |" for s in shown]
        if len(shown) < len(rows):
            lines.append(f"[cut: {len(rows) - len(shown)} more rows, run with --full]")
        lines.append("")
    lines += ["## Body", "", cut(issue.body.strip(), None if full else body_limit) or "(empty)", ""]
    decisions = sorted(
        [(issue.parent_number, c) for c in issue.parent_comments if is_decision(c.body)] + [(issue.number, c) for c in issue.comments if is_decision(c.body)],
        key=lambda pair: pair[1].at or pair[1].date,
    )
    if decisions:
        lines += [f"## Decisions ({len(decisions)})", ""]
        for number, comment in decisions:
            lines += [f"### #{number} @{comment.author}, {comment.date}", "", comment.body.strip(), ""]
    others = [c for c in issue.comments if not is_decision(c.body)]
    other_total = issue.comment_total - (len(issue.comments) - len(others))
    comments = others if full else others[-comments_shown:]
    if not comments:
        lines.append("## Comments (none)")
    else:
        lines += [f"## Comments ({len(comments)} of {other_total}, newest last)", ""]
        for comment in comments:
            lines += [f"### @{comment.author}, {comment.date}", "", cut(comment.body.strip(), None if full else comment_limit), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def review_line(pr: int, task: TaskMatch, spec: SpecMatch, standard: str | None) -> str:
    parts = [f"issue #{task.number}" if task.number is not None else "", f"PR #{pr}"]
    parts += [f"spec {spec.path}" if spec.path else "", f"standard {standard}" if standard else ""]
    return "/agent-skills:review " + ", ".join(part for part in parts if part)


def task_line(task: TaskMatch, title: str) -> str:
    if task.number is None:
        return "none"
    named = f"#{task.number} {title}".rstrip()
    return f"{named} (from {task.source}) (guess)" if task.guess else f"{named} (from {task.source})"


def pr_report(pr: PullRequest, task: TaskMatch, task_title: str, spec: SpecMatch, standard: str | None, full: bool) -> str:
    reviews = ", ".join(f"@{r.author} {r.state} {r.date}" for r in pr.reviews) or "none"
    lines = [
        f"# PR #{pr.number} {pr.title} [{pr.state}]",
        f"- URL: {pr.url}",
        f"- Base: {pr.base}",
        f"- Head: {pr.head}",
        f"- Draft: {'yes' if pr.draft else 'no'}",
        f"- Checks: {pr.checks}",
        f"- Reviews: {reviews}",
        f"- Task: {task_line(task, task_title)}",
        f"- Spec: {spec_line(spec)}",
        f"- Standard: {standard or 'none'}",
        "",
        f"## Files ({pr.file_total}, +{sum(f.additions for f in pr.files)} -{sum(f.deletions for f in pr.files)})",
        "",
    ]
    if pr.files:
        lines += ["| File | + | - |", "| --- | --- | --- |"]
        lines += [f"| {cell(f.path)} | {f.additions} | {f.deletions} |" for f in pr.files]
        if len(pr.files) < pr.file_total:
            lines.append(f"[{pr.file_total - len(pr.files)} more files not read]")
        lines.append("")
    lines += [f"## Commits ({len(pr.commits)} of {pr.commit_total}, newest last)", ""]
    lines += [f"- {headline}" for headline in pr.commits]
    lines += ["", "## Body", "", cut(pr.body.strip(), None if full else BODY_LIMIT) or "(empty)", ""]
    lines += [f"Check out: gh pr checkout {pr.number}", f"Review: {review_line(pr.number, task, spec, standard)}"]
    return "\n".join(lines) + "\n"


def review_notes(task: TaskMatch, spec: SpecMatch, standard: str | None) -> list[str]:
    left_out = []
    if task.number is None:
        left_out += ["issue (no task found)", "spec (no task found)"]
    elif spec.path is None:
        left_out.append(f"spec ({spec_problem(task.number, spec)})")
    if standard is None:
        left_out.append("standard (no CODING_STANDARDS.md, AGENTS.md or CLAUDE.md)")
    notes = [f"Left out of the review line: {', '.join(left_out)}."] if left_out else []
    if task.guess:
        notes.append(f"Task #{task.number} is from the {task.source} (guess).")
    if spec.guess:
        notes.append(spec_guess_note(spec))
    return notes


def spec_problem(number: int, spec: SpecMatch) -> str:
    if spec.candidates:
        return f"#{number} has no spec. Candidates: {', '.join(spec.candidates)}"
    return f"#{number} has no spec"


def spec_guess_note(spec: SpecMatch) -> str:
    return f"Spec {spec.path} is from the file name (guess)."


def ac_report(boxes: Sequence[Box]) -> str:
    lines = [f"{index}. [{'x' if box.ticked else ' '}] {box.text}" for index, box in enumerate(boxes, 1)]
    lines.append(f"Ticked: {sum(box.ticked for box in boxes)} of {len(boxes)}")
    return "\n".join(lines) + "\n"


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def evidence_report(number: int, found: Evidence) -> str:
    if not found.configured:
        return f"PR #{number} needs no evidence: docs/agents/workflow.md has no `## Evidence paths` heading.\n"
    if not found.touched:
        return f"PR #{number} needs no evidence: it changes no evidence path.\n"
    return f"PR #{number} has evidence: it changes {plural(len(found.touched), 'evidence path')}, and its `## Verification` section has {plural(found.images, 'image')}.\n"


def added_report(number: int, branch: str, commit: str, urls: Sequence[str]) -> str:
    lines = [f"Added {plural(len(urls), 'image')} to the `## Verification` section of PR #{number}, from the {branch} branch at {commit[:8]}:", *urls]
    return "\n".join(lines) + "\n"


def land_refusal(number: int, reasons: Sequence[str]) -> str:
    return "\n".join([f"Not landed: PR #{number}", *(f"- {reason}" for reason in reasons)])


def land_report(number: int, url: str, base: str, notes: Sequence[str]) -> str:
    return "\n".join([f"Landed PR #{number} into {base}: {url}", *notes]) + "\n"


def claim_report(number: int, assigned: str, branch: str | None, default: str, commit: str) -> str:
    sentences = {"now": f"Claimed #{number} for @me.", "already": f"#{number} is already assigned to @me.", "skipped": ""}[assigned]
    if branch:
        sentences += f" Branch {branch} from origin/{default} at {commit}."
    return (sentences.strip() or f"Nothing changed for #{number}.") + "\n"


def issue_command(group: str, row: IssueRow) -> str:
    if group == "Build":
        return f"/agent-skills:build #{row.number}"
    if group == "Plan":
        return f"/agent-skills:plan #{row.number}, spec {row.spec}"
    if group == "Spec":
        return f"/agent-skills:spec #{row.number}"
    return f"/agent-skills:idea-refine #{row.number}"


def group_table(name: str, rows: Sequence[tuple[str, str, str]], notes: Sequence[str] = ()) -> list[str]:
    lines = [f"## {name}", "", "| # | Title | Command |", "| --- | --- | --- |"]
    lines += [f"| {number} | {cell(title)} | `{command}` |" for number, title, command in rows[:NEXT_ROWS_SHOWN]]
    left_out = len(rows) - min(len(rows), NEXT_ROWS_SHOWN)
    lines += ["", f"Left out: {left_out} {'row' if left_out == 1 else 'rows'}." if left_out else "Left out: none."]
    return lines + [*notes, ""]


def review_guesses(row: ReviewRow) -> list[str]:
    guesses = []
    if row.task.number is None:
        guesses.append(f"- PR #{row.pr}: no task found.")
    elif row.task.guess:
        guesses.append(f"- PR #{row.pr}: task #{row.task.number} is from the branch name (guess).")
    if row.spec.guess:
        guesses.append(f"- PR #{row.pr}: spec {row.spec.path} is from the file name (guess).")
    return guesses


def next_report(repo: str, groups: Groups, standard: str | None, step: ReviewRow | IssueRow | None) -> str:
    lines = [f"# What to do next in {repo}", ""]
    if groups.review:
        rows = [(f"#{r.pr}", r.title, review_line(r.pr, r.task, r.spec, standard)) for r in groups.review]
        shown = groups.review[:NEXT_ROWS_SHOWN]
        notes = [f"Spec candidates for PR #{r.pr}: {', '.join(r.spec.candidates)}." for r in shown if r.spec.candidates]
        lines += group_table("Review", rows, notes)
    if groups.build:
        lines += group_table("Build", [(f"#{r.number} (frontier)" if r.frontier else f"#{r.number}", r.title, issue_command("Build", r)) for r in groups.build])
    for name, rows in (("Plan", groups.plan), ("Spec", groups.spec), ("Idea", groups.idea)):
        if rows:
            lines += group_table(name, [(f"#{r.number}", r.title, issue_command(name, r)) for r in rows])
    if not any((groups.review, groups.build, groups.plan, groups.spec, groups.idea)):
        lines += ["No open PR or issue fits a group.", ""]
    lines += ["## Next", ""]
    if isinstance(step, ReviewRow):
        lines += ["```", f"gh pr checkout {step.pr}", review_line(step.pr, step.task, step.spec, standard), "```"]
    elif isinstance(step, IssueRow):
        lines += ["```", issue_command("Build", step), "```"]
    else:
        lines.append("none (no open PR and no frontier task)")
    guesses = [guess for row in groups.review for guess in review_guesses(row)]
    lines += ["", "## Guesses", "", *(guesses or ["none"])]
    return "\n".join(lines) + "\n"
