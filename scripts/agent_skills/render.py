from collections.abc import Sequence

from agent_skills.tracker import Frontier, SubIssue


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
