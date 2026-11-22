import re
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import quote

from agent_skills.brief import sections
from agent_skills.tracker import is_decision

EVIDENCE_BRANCH = "evidence"
MERGE_METHOD = "merge"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
ITEM = re.compile(r"\s*[-*]\s+`([^`]+)`\s*$")
VERIFY_LINE = re.compile(r"\s*Verify command:\s*(\S.*?)\s*$", re.IGNORECASE)
HEADING = re.compile(r"(#{1,6})\s+(.*?)\s*$")
IMAGE = re.compile(r"!\[[^\]]*\]\(\s*[^)\s]+[^)]*\)|<img\b[^>]*\bsrc\s*=", re.IGNORECASE)


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
    for section in sections(text):
        first, _, rest = section.partition("\n")
        if first.strip().lower() == f"## {title}".lower():
            return rest
    return None


def listed(section: str | None) -> tuple[str, ...]:
    return tuple(match[1] for line in (section or "").splitlines() if (match := ITEM.match(line)))


def checks(workflow: str) -> tuple[str, ...]:
    return listed(workflow_section(workflow, "Checks"))


def verify_command(section: str) -> str | None:
    return next((match[1] for line in section.splitlines() if (match := VERIFY_LINE.match(line))), None)


def glob_pattern(glob: str) -> re.Pattern[str]:
    """`*` and `?` stay inside one path part, `**` crosses parts, and a glob that ends with `/` covers the whole folder."""
    if glob.endswith("/"):
        glob += "**"
    pattern, index = "", 0
    while index < len(glob):
        if glob.startswith("**/", index):
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


def verification_span(lines: Sequence[str]) -> tuple[int, int] | None:
    """The line range of the Verification section of a pull request body: its heading, up to the next heading of the same or a higher level."""
    start, level = None, 0
    for index, line in enumerate(lines):
        heading = HEADING.match(line)
        if heading is None:
            continue
        if start is None and heading[2].lower().startswith("verification"):
            start, level = index, len(heading[1])
        elif start is not None and len(heading[1]) <= level:
            return start, index
    return (start, len(lines)) if start is not None else None


def verification_images(body: str) -> int:
    lines = body.splitlines()
    span = verification_span(lines)
    return len(IMAGE.findall("\n".join(lines[span[0] : span[1]]))) if span else 0


def evidence(workflow: str, paths: Sequence[str], body: str) -> Evidence:
    section = workflow_section(workflow, "Evidence paths")
    if section is None:
        return Evidence(configured=False)
    return Evidence(True, touched(paths, listed(section)), verification_images(body), verify_command(section))


def image_url(repo: str, commit: str, folder: str, name: str) -> str:
    return f"https://github.com/{repo}/blob/{commit}/{quote(f'{folder}/{name}')}?raw=true"


def with_images(body: str, images: Sequence[tuple[str, str]]) -> str:
    """The body with one image per (alt text, URL) at the end of its Verification section. A body without the section gets one at its end."""
    newline = "\r\n" if "\r\n" in body else "\n"
    lines = body.split(newline)
    block = [line for alt, url in images for line in (f"![{alt}]({url})", "")]
    span = verification_span(lines)
    if span is None:
        kept = body.rstrip().split(newline) if body.strip() else []
        return newline.join([*kept, *([""] if kept else []), "## Verification", "", *block])
    start, end = span
    section = lines[start:end]
    while section and not section[-1].strip():
        section.pop()
    return newline.join([*lines[:start], *section, "", *block, *lines[end:]])


def has_review_decision(number: int, comments: Sequence[str]) -> bool:
    named = re.compile(rf"decisions from the review of PR #{number}\b", re.IGNORECASE)
    return any(is_decision(body) and named.search(body.split("\n", 1)[0]) for body in comments)


def refusals(pull: LandPull, branch: str, commit: str, dirty: bool, behind: int, found: Evidence, commands: Sequence[str]) -> list[str]:
    """Every reason that stops `land` before it runs the checks. An empty list lets it go on."""
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
    if not has_review_decision(pull.number, pull.comments):
        reasons.append(f"no review decision comment names PR #{pull.number}. The review posts it with `agent-skills decide <issue> --from review --pr {pull.number}`.")
    if found.missing:
        reasons.append(evidence_gap(pull.number, found))
    if not commands:
        reasons.append("docs/agents/workflow.md has no `## Checks` heading with a command, so the checks of the repo cannot run.")
    return reasons


def evidence_gap(number: int, found: Evidence) -> str:
    shown = ", ".join(found.touched[:3]) + (f" and {len(found.touched) - 3} more" if len(found.touched) > 3 else "")
    verify = f" Make the screenshots with {found.verify}." if found.verify else ""
    return (
        f"it changes {len(found.touched)} evidence path{'s' if len(found.touched) != 1 else ''} ({shown}), and its body has no `## Verification` section with an image."
        f"{verify} Then run `agent-skills evidence {number} --add <image>...`."
    )
