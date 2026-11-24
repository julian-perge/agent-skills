import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import quote


EVIDENCE_BRANCH = "evidence"
MERGE_METHOD = "merge"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
ITEM = re.compile(r"\s*[-*]\s+`([^`]+)`\s*$")
LIST_LINE = re.compile(r"\s*(?:[-*+]|\d+[.)])\s+\S")
SHELL_WORDS = frozenset({"&&", "||", "|", ";", ">", ">>", "<"})
FENCE = re.compile(r"\s{0,3}(```|~~~)")
CODE_SPAN = re.compile(r"`[^`]*`")
VERIFY_LINE = re.compile(r"\s*Verify command:\s*(\S.*?)\s*$", re.IGNORECASE)
REVIEWED_HEAD = re.compile(r"\s*Reviewed head:\s*([0-9a-f]{40})\s*$", re.IGNORECASE)
REVIEWER = re.compile(r"\s*Reviewer:\s*(\S.*?)\s*$", re.IGNORECASE)
HEADING = re.compile(r"(#{1,6})\s+(.*?)\s*$")
IMAGE = re.compile(r"!\[[^\]]*\]\(\s*<?https?://[^)\s]+[^)]*\)|<img\b[^>]*\bsrc\s*=\s*[\"']?https?://", re.IGNORECASE)


@dataclass(frozen=True)
class LandPull:
    number: int
    title: str
    state: str = "OPEN"
    draft: bool = False
    url: str = ""
    body: str = ""
    base: str = ""
    head: str = ""
    head_commit: str = ""
    mergeable: str = "MERGEABLE"
    paths: tuple[str, ...] = ()
    comments: tuple[str, ...] = ()


@dataclass(frozen=True)
class Evidence:
    configured: bool
    touched: tuple[str, ...] = ()
    images: int = 0
    verify: str | None = None

    @property
    def missing(self) -> bool:
        return bool(self.touched) and self.images == 0


def workflow_section(text: str, title: str) -> str | None:
    """The text under the heading `## <title>` of docs/agents/workflow.md, or None when the file has no such heading."""
    lines = text.splitlines(keepends=True)
    starts = [index for index, outside in enumerate(outside_fences(lines)) if outside and lines[index].startswith("## ")]
    for start, end in zip(starts, [*starts[1:], len(lines)]):
        if lines[start].strip().lower() == f"## {title}".lower():
            return "".join(lines[start + 1 : end])
    return None


def listed(section: str | None) -> tuple[str, ...]:
    return tuple(match[1] for line in (section or "").splitlines() if (match := ITEM.match(line)))


def checks(workflow: str) -> tuple[str, ...]:
    return listed(workflow_section(workflow, "Checks"))


def command_problem(command: str) -> str | None:
    if command.startswith("<") and command.endswith(">"):
        return "is the placeholder of the seed, not a command"
    try:
        words = shlex.split(command)
    except ValueError as error:
        return f"does not parse as a command ({error})"
    if not words:
        return "is empty"
    if SHELL_WORDS.intersection(words):
        return "uses shell syntax, and a command runs without a shell. Wrap it in bash -c '...'"
    return None


def glob_problem(glob: str) -> str | None:
    if glob.startswith("<") and glob.endswith(">"):
        return "is the placeholder of the seed, not a glob"
    if glob.startswith(("/", "./")):
        return "must start at the repo root with no leading / or ./"
    if any(char in glob for char in "[{\\"):
        return "uses [ ], { } or a backslash, and only *, ** and ? are read"
    return None


def workflow_problems(workflow: str) -> list[str]:
    """Each list item under `## Checks` or `## Evidence paths` that `land` and `evidence` would skip or misread without a word."""
    problems = []
    for title, kind, problem in (("Checks", "command", command_problem), ("Evidence paths", "glob", glob_problem)):
        for line in (workflow_section(workflow, title) or "").splitlines():
            if not LIST_LINE.match(line):
                continue
            item = ITEM.match(line)
            reason = problem(item[1]) if item else f"is not one {kind} in backticks with nothing after it"
            if reason:
                problems.append(f"under `## {title}`, the list item {line.strip()!r} {reason}.")
    return problems


def verify_command(section: str) -> str | None:
    return next((match[1] for line in section.splitlines() if (match := VERIFY_LINE.match(line))), None)


def glob_pattern(glob: str) -> re.Pattern[str]:
    """`*` and `?` stay inside one path part, `**` crosses parts, and a glob that ends with `/` covers the whole folder."""
    if glob.endswith("/"):
        glob += "**"
    pattern, index = "", 0
    while index < len(glob):
        if glob.startswith("**/", index) and (index == 0 or glob[index - 1] == "/"):
            pattern, index = pattern + "(?:.*/)?", index + 3
        elif glob.startswith("**", index):
            pattern, index = pattern + ".*", index + 2
        elif glob[index] == "*":
            pattern, index = pattern + "[^/]*", index + 1
        elif glob[index] == "?":
            pattern, index = pattern + "[^/]", index + 1
        else:
            pattern, index = pattern + re.escape(glob[index]), index + 1
    return re.compile(pattern)


def touched(paths: Sequence[str], globs: Sequence[str]) -> tuple[str, ...]:
    patterns = [glob_pattern(glob) for glob in globs]
    return tuple(path for path in paths if any(pattern.fullmatch(path) for pattern in patterns))


def outside_fences(lines: Sequence[str]) -> list[bool]:
    """For each line, whether it is outside every fenced code block. The fence lines themselves are inside."""
    marks, fence = [], None
    for line in lines:
        mark = FENCE.match(line)
        marks.append(fence is None and mark is None)
        if mark and fence is None:
            fence = mark[1]
        elif mark and mark[1] == fence:
            fence = None
    return marks


def verification_span(lines: Sequence[str]) -> tuple[int, int] | None:
    """The line range of the Verification section of a pull request body: its heading, up to the next heading of the same or a higher level.

    A line that starts with # inside a fenced code block is a comment of that code, not a heading.
    """
    start, level = None, 0
    for index, (line, outside) in enumerate(zip(lines, outside_fences(lines))):
        heading = HEADING.match(line) if outside else None
        if heading is None:
            continue
        if start is None and heading[2].lower().startswith("verification"):
            start, level = index, len(heading[1])
        elif start is not None and len(heading[1]) <= level:
            return start, index
    return (start, len(lines)) if start is not None else None


def verification_images(body: str) -> int:
    """How many images a reader of the pull request sees in its Verification section: web URLs only, and none inside code."""
    lines = body.splitlines()
    span = verification_span(lines)
    if span is None:
        return 0
    outside = outside_fences(lines)
    shown = [CODE_SPAN.sub("", lines[index]) for index in range(*span) if outside[index]]
    return len(IMAGE.findall("\n".join(shown)))


def evidence(workflow: str, paths: Sequence[str], body: str) -> Evidence:
    section = workflow_section(workflow, "Evidence paths")
    if section is None:
        return Evidence(configured=False)
    return Evidence(True, touched(paths, listed(section)), verification_images(body), verify_command(section))


def image_url(repo: str, commit: str, folder: str, name: str) -> str:
    return f"https://github.com/{repo}/blob/{commit}/{quote(f'{folder}/{name}')}?raw=true"


def with_images(body: str, images: Sequence[tuple[str, str]]) -> str:
    """The body with one image per (alt text, URL) at the end of its Verification section. A body without the section gets one at its end.

    Every other line keeps its own line end. Blank lines at the end of the section become one.
    """
    newline = "\r\n" if "\r\n" in body else "\n"
    block = "".join(f"{newline}![{alt.replace('[', '(').replace(']', ')')}]({url}){newline}" for alt, url in images)
    lines = body.splitlines(keepends=True)
    span = verification_span([line.rstrip("\r\n") for line in lines])
    if span is None:
        kept = body.rstrip()
        return (kept + newline * 2 if kept else "") + f"## Verification{newline}{block}"
    start, end = span
    last = end
    while last > start + 1 and not lines[last - 1].strip():
        last -= 1
    section = "".join(lines[:last])
    rest = "".join(lines[end:])
    if not section.endswith(("\r", "\n")):
        section += newline
    return section + block + (newline + rest if rest else "")


def review_decision(number: int, comments: Sequence[str]) -> str | None:
    """The newest comment that `agent-skills decide --from review --pr <number>` posts: its whole first line names this review. `comments` are oldest first."""
    first_line = re.compile(rf"[#*\s]*decisions from the review of PR #{number}[*\s]*$", re.IGNORECASE)
    return next((body for body in reversed(comments) if first_line.match(body.split("\n", 1)[0])), None)


def review_line(body: str, pattern: re.Pattern[str]) -> str | None:
    return next((match[1] for line in body.splitlines() if (match := pattern.match(line))), None)


def review_gap(number: int, comments: Sequence[str]) -> str | None:
    """Why no review decision comment can show which commit the review covers and who reviewed it, or None when the newest one shows both."""
    decide = f"`agent-skills decide <issue or PR> --from review --pr {number} --reviewer <reviewer>`"
    decision = review_decision(number, comments)
    if decision is None:
        return f"no review decision comment names PR #{number} on the pull request, on an issue it closes or on the parent of one. The review posts it with {decide}."
    missing = [f"no `{label}` line" for label, pattern in (("Reviewed head:", REVIEWED_HEAD), ("Reviewer:", REVIEWER)) if review_line(decision, pattern) is None]
    if missing:
        return f"the newest review decision comment of PR #{number} has {' and '.join(missing)}. The reviewer posts the decision again with {decide}, which writes both lines."
    return None


def refusals(
    pull: LandPull, branch: str, commit: str, dirty: bool, behind: int, found: Evidence, commands: Sequence[str], blocked: Sequence[str] = (), stale: Sequence[str] = ()
) -> list[str]:
    """Every reason that stops `land` before it runs the checks. An empty list lets it go on.

    `blocked` holds the reasons why the checkout could not move to the base branch after the merge. `stale` holds the reasons why
    the review decision does not cover the change at the head of the pull request.
    """
    if pull.state != "OPEN":
        return [f"the pull request is {pull.state.lower()}."]
    reasons = []
    if pull.draft:
        reasons.append("the pull request is a draft.")
    if branch != pull.head:
        reasons.append(f"this checkout is on {branch}, not on the PR branch {pull.head}. Run `gh pr checkout {pull.number}`.")
    elif commit != pull.head_commit:
        reasons.append(f"HEAD is {commit[:8]} and the pull request is at {pull.head_commit[:8]}. Push or pull until they are the same commit.")
    if dirty:
        reasons.append("the working tree has changes. Commit and push them, or stash them.")
    if behind and branch == pull.head and commit == pull.head_commit:
        reasons.append(
            f"the PR branch is {behind} commit{'s' if behind != 1 else ''} behind {pull.base}, so the checks would not test the merged code. "
            f"Run `git merge origin/{pull.base}`, push, and run the command again."
        )
    if pull.mergeable == "CONFLICTING":
        reasons.append(f"the pull request has merge conflicts with {pull.base}.")
    elif pull.mergeable != "MERGEABLE":
        reasons.append("GitHub has not worked out yet whether the pull request merges cleanly. Run the command again.")
    gap = review_gap(pull.number, pull.comments)
    reasons += [gap] if gap else stale
    if found.missing:
        reasons.append(evidence_gap(pull.number, found))
    if not commands:
        reasons.append("docs/agents/workflow.md has no `## Checks` heading with a command, so the checks of the repo cannot run.")
    return [*reasons, *blocked]


def evidence_gap(number: int, found: Evidence) -> str:
    shown = ", ".join(found.touched[:3]) + (f" and {len(found.touched) - 3} more" if len(found.touched) > 3 else "")
    verify = f" Make the screenshots with {found.verify}." if found.verify else ""
    return (
        f"it changes {len(found.touched)} evidence path{'s' if len(found.touched) != 1 else ''} ({shown}), and its body has no `## Verification` section with an image."
        f"{verify} Then run `agent-skills evidence {number} --add <image>...`."
    )
