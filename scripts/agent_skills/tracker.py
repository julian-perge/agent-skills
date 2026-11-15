import re
from collections.abc import Sequence
from dataclasses import dataclass

SPEC_LINE = re.compile(r"^[\s*_>-]*spec\b[^\n]*?(spec/[\w./-]+?\.md)", re.IGNORECASE | re.MULTILINE)
SPEC_PATH = re.compile(r"spec/[\w./-]+?\.md")
SPEC_NUMBER = re.compile(r"spec/(\d+)-")


@dataclass(frozen=True)
class SubIssue:
    number: int
    title: str
    state: str
    assignees: tuple[str, ...]
    open_blockers: int


@dataclass(frozen=True)
class Frontier:
    number: int | None
    reason: str = ""


def frontier(subs: Sequence[SubIssue]) -> Frontier:
    if not subs:
        return Frontier(None, "no sub-issues")
    open_subs = [s for s in subs if s.state == "OPEN"]
    if not open_subs:
        return Frontier(None, f"all {len(subs)} sub-issues are closed")
    ready = [s.number for s in open_subs if not s.assignees and s.open_blockers == 0]
    if ready:
        return Frontier(min(ready))
    blocked = sum(1 for s in open_subs if s.open_blockers)
    assigned = sum(1 for s in open_subs if s.assignees)
    return Frontier(None, f"each open sub-issue is blocked or assigned: {blocked} blocked, {assigned} assigned")


@dataclass(frozen=True)
class Link:
    number: int
    state: str


@dataclass(frozen=True)
class Comment:
    author: str
    date: str
    body: str


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    state: str = "OPEN"
    url: str = ""
    body: str = ""
    labels: tuple[str, ...] = ()
    assignees: tuple[str, ...] = ()
    parent_number: int | None = None
    parent_title: str = ""
    parent_body: str = ""
    sub_issues: tuple[SubIssue, ...] = ()
    sub_issue_total: int = 0
    sub_issue_completed: int = 0
    blockers: tuple[Link, ...] = ()
    pull_requests: tuple[Link, ...] = ()
    comments: tuple[Comment, ...] = ()
    comment_total: int = 0


@dataclass(frozen=True)
class SpecMatch:
    path: str | None
    source: str
    guess: bool
    candidates: tuple[str, ...] = ()


def first_spec_path(text: str) -> str | None:
    line = SPEC_LINE.search(text)
    if line:
        return line[1]
    path = SPEC_PATH.search(text)
    return path[0] if path else None


def spec_number(path: str) -> int | None:
    match = SPEC_NUMBER.match(path)
    return int(match[1]) if match else None


def spec_for(issue: Issue, spec_files: frozenset[str]) -> SpecMatch:
    for text, source in ((issue.body, "issue body"), (issue.parent_body, "parent body")):
        path = first_spec_path(text)
        if path in spec_files:
            return SpecMatch(path, source, guess=False)
    numbers = {issue.number} if issue.parent_number is None else {issue.number, issue.parent_number}
    candidates = tuple(sorted(p for p in spec_files if spec_number(p) in numbers))
    if len(candidates) == 1:
        return SpecMatch(candidates[0], "file name", guess=True)
    return SpecMatch(None, "none", guess=False, candidates=candidates)
