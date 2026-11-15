from collections.abc import Sequence

from agent_skills.tracker import Frontier, Issue, SpecMatch, SubIssue

BODY_LIMIT = 2000
COMMENT_LIMIT = 600
COMMENTS_SHOWN = 3
ROWS_SHOWN = 10


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


def issue_report(issue: Issue, spec: SpecMatch, full: bool) -> str:
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
    lines += ["## Body", "", cut(issue.body.strip(), None if full else BODY_LIMIT) or "(empty)", ""]
    comments = issue.comments if full else issue.comments[-COMMENTS_SHOWN:]
    if not comments:
        lines.append("## Comments (none)")
    else:
        lines += [f"## Comments ({len(comments)} of {issue.comment_total}, newest last)", ""]
        for comment in comments:
            lines += [f"### @{comment.author}, {comment.date}", "", cut(comment.body.strip(), None if full else COMMENT_LIMIT), ""]
    return "\n".join(lines).rstrip("\n") + "\n"
