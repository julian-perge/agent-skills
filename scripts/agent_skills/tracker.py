import re
from collections.abc import Sequence
from dataclasses import dataclass

SPEC_LINE = re.compile(r"^[\s*_>-]*spec\b[^\n]*?(spec/[\w./-]+?\.md)", re.IGNORECASE | re.MULTILINE)
SPEC_PATH = re.compile(r"spec/[\w./-]+?\.md")
SPEC_NUMBER = re.compile(r"spec/(\d+)-")
CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+#(\d+)\b", re.IGNORECASE)
BRANCH_NUMBER = re.compile(r"^[\w.-]+/(\d+)-")
STANDARD_FILES = ("CODING_STANDARDS.md", "AGENTS.md", "CLAUDE.md")
NOT_FOR_SPEC = frozenset({"ready-for-agent", "ready-for-human", "needs-info", "needs-triage", "wontfix"})


@dataclass(frozen=True)
class SubIssue:
    number: int
    title: str
    state: str
    assignees: tuple[str, ...]
    open_blockers: int
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class Frontier:
    number: int | None
    reason: str = ""


def ready_to_build(labels: Sequence[str], assigned: bool, open_blockers: int) -> bool:
    return "ready-for-agent" in labels and not assigned and open_blockers == 0


def frontier(subs: Sequence[SubIssue]) -> Frontier:
    if not subs:
        return Frontier(None, "no sub-issues")
    open_subs = [s for s in subs if s.state == "OPEN"]
    if not open_subs:
        return Frontier(None, f"all {len(subs)} sub-issues are closed")
    ready = [s.number for s in open_subs if ready_to_build(s.labels, bool(s.assignees), s.open_blockers)]
    if ready:
        return Frontier(min(ready))
    counts = (
        (sum(1 for s in open_subs if "ready-for-agent" not in s.labels), "without ready-for-agent"),
        (sum(1 for s in open_subs if s.open_blockers), "blocked"),
        (sum(1 for s in open_subs if s.assignees), "assigned"),
    )
    found = ", ".join(f"{count} {what}" for count, what in counts if count)
    return Frontier(None, f"no open sub-issue is ready-for-agent, unblocked and unassigned: {found}")


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


@dataclass(frozen=True)
class FileChange:
    path: str
    additions: int
    deletions: int


@dataclass(frozen=True)
class Review:
    author: str
    state: str
    date: str


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    state: str = "OPEN"
    draft: bool = False
    url: str = ""
    body: str = ""
    base: str = ""
    head: str = ""
    closing: tuple[Issue, ...] = ()
    files: tuple[FileChange, ...] = ()
    file_total: int = 0
    commits: tuple[str, ...] = ()
    commit_total: int = 0
    checks: str = "none"
    reviews: tuple[Review, ...] = ()


@dataclass(frozen=True)
class TaskMatch:
    number: int | None
    source: str
    guess: bool = False


def pr_task(closing: Sequence[int], body: str, head: str) -> TaskMatch:
    if closing:
        return TaskMatch(closing[0], "closing reference")
    closes = CLOSES.search(body)
    if closes:
        return TaskMatch(int(closes[1]), "body")
    branch = BRANCH_NUMBER.match(head)
    if branch:
        return TaskMatch(int(branch[1]), "branch name", guess=True)
    return TaskMatch(None, "none")


def standard_file(root_files: frozenset[str]) -> str | None:
    return next((name for name in STANDARD_FILES if name in root_files), None)


def slug(title: str) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower().replace("'", "").replace("\u2019", ""))[:5]
    while len(words) > 1 and len("-".join(words)) > 40:
        words.pop()
    return "-".join(words)[:40]


def branch_type(labels: Sequence[str], override: str | None) -> str:
    if override:
        return override
    return "fix" if "bug" in labels else "feat"


def branch_name(issue: Issue, override: str | None) -> str:
    name = slug(issue.title)
    kind = branch_type(issue.labels, override)
    return f"{kind}/{issue.number}-{name}" if name else f"{kind}/{issue.number}"


def claim_refusal(issue: Issue, me: str) -> str | None:
    if issue.state != "OPEN":
        return f"#{issue.number} is closed."
    others = [login for login in issue.assignees if login != me]
    if others:
        return f"#{issue.number} is assigned to {', '.join(f'@{login}' for login in others)}."
    blockers = [f"#{b.number}" for b in issue.blockers if b.state == "OPEN"]
    if blockers:
        return f"#{issue.number} has open blockers: {', '.join(blockers)}."
    return None


@dataclass(frozen=True)
class TrackerIssue:
    number: int
    title: str
    body: str = ""
    labels: tuple[str, ...] = ()
    assigned: bool = False
    parent_number: int | None = None
    parent_body: str = ""
    sub_issue_total: int = 0
    open_blockers: int = 0
    open_pull_requests: tuple[int, ...] = ()

    def lookup(self) -> Issue:
        return Issue(self.number, self.title, body=self.body, parent_number=self.parent_number, parent_body=self.parent_body)


@dataclass(frozen=True)
class OpenPull:
    number: int
    title: str
    head: str = ""
    body: str = ""
    draft: bool = False
    created_at: str = ""


@dataclass(frozen=True)
class ReviewRow:
    pr: int
    title: str
    task: TaskMatch
    spec: SpecMatch


@dataclass(frozen=True)
class IssueRow:
    number: int
    title: str
    spec: str | None = None
    frontier: bool = False


@dataclass(frozen=True)
class Groups:
    review: tuple[ReviewRow, ...] = ()
    build: tuple[IssueRow, ...] = ()
    plan: tuple[IssueRow, ...] = ()
    spec: tuple[IssueRow, ...] = ()
    idea: tuple[IssueRow, ...] = ()


def review_rows(pulls: Sequence[OpenPull], issues: Sequence[TrackerIssue], spec_files: frozenset[str]) -> tuple[ReviewRow, ...]:
    by_number = {issue.number: issue for issue in issues}
    rows = []
    for pull in sorted((p for p in pulls if not p.draft), key=lambda p: (p.created_at, p.number)):
        task = pr_task((), pull.body, pull.head)
        spec = SpecMatch(None, "none", guess=False)
        if task.number is not None:
            issue = by_number.get(task.number)
            spec = spec_for(issue.lookup() if issue else Issue(task.number, ""), spec_files)
        rows.append(ReviewRow(pull.number, pull.title, task, spec))
    return tuple(rows)


def is_buildable(issue: TrackerIssue) -> bool:
    return ready_to_build(issue.labels, issue.assigned, issue.open_blockers) and not issue.open_pull_requests


def specs_by_issue(spec_files: frozenset[str]) -> dict[int, list[str]]:
    grouped: dict[int, list[str]] = {}
    for path in sorted(spec_files):
        number = spec_number(path)
        if number is not None:
            grouped.setdefault(number, []).append(path)
    return grouped


def plan_candidates(pulls: Sequence[OpenPull], issues: Sequence[TrackerIssue], spec_files: frozenset[str]) -> list[int]:
    taken = {row.task.number for row in review_rows(pulls, issues, spec_files)}
    with_specs = specs_by_issue(spec_files)
    return sorted(i.number for i in issues if i.number in with_specs and i.number not in taken and not is_buildable(i))


def frontier_marks(issues: Sequence[TrackerIssue], build: Sequence[TrackerIssue]) -> set[int]:
    lowest: dict[int, int] = {}
    for issue in issues:
        if issue.parent_number is not None and ready_to_build(issue.labels, issue.assigned, issue.open_blockers):
            lowest[issue.parent_number] = min(lowest.get(issue.parent_number, issue.number), issue.number)
    build_numbers = {issue.number for issue in build}
    return {n for n in lowest.values() if n in build_numbers} | {i.number for i in build if i.parent_number is None}


def group(
    pulls: Sequence[OpenPull],
    issues: Sequence[TrackerIssue],
    spec_files: frozenset[str],
    sub_issue_bodies: dict[int, Sequence[str]],
) -> Groups:
    ordered = sorted(issues, key=lambda i: i.number)
    review = review_rows(pulls, issues, spec_files)
    placed = {row.task.number for row in review if row.task.number is not None}

    buildable = [i for i in ordered if i.number not in placed and is_buildable(i)]
    marks = frontier_marks(issues, buildable)
    build = sorted((IssueRow(i.number, i.title, frontier=i.number in marks) for i in buildable), key=lambda r: (not r.frontier, r.number))
    placed |= {row.number for row in build}

    with_specs = specs_by_issue(spec_files)
    plan = []
    for issue in ordered:
        if issue.number in placed or issue.number not in with_specs:
            continue
        bodies = sub_issue_bodies.get(issue.number, ())
        plan += [IssueRow(issue.number, issue.title, spec=path) for path in with_specs[issue.number] if not any(path in body for body in bodies)]
    placed |= {row.number for row in plan}

    spec = [
        IssueRow(i.number, i.title)
        for i in ordered
        if i.number not in placed
        and i.parent_number is None
        and i.sub_issue_total == 0
        and not NOT_FOR_SPEC.intersection(i.labels)
        and spec_for(i.lookup(), spec_files).path is None
    ]
    placed |= {row.number for row in spec}

    idea = [IssueRow(i.number, i.title) for i in ordered if i.number not in placed and "needs-triage" in i.labels]
    return Groups(review, tuple(build), tuple(plan), tuple(spec), tuple(idea))


def next_step(groups: Groups) -> ReviewRow | IssueRow | None:
    if groups.review:
        return groups.review[0]
    frontiers = [row for row in groups.build if row.frontier]
    return min(frontiers, key=lambda row: row.number) if frontiers else None
