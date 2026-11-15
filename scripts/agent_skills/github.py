import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from agent_skills import CliError
from agent_skills.tracker import Comment, Issue, Link, SubIssue

REMOTE = re.compile(r"[/:](?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?/?$")

SUB_ISSUE_FIELDS = """
        number title state
        assignees(first: 5) { nodes { login } }
        issueDependenciesSummary { blockedBy }"""

FRONTIER_QUERY = f"""query($owner: String!, $name: String!, $number: Int!) {{
  repository(owner: $owner, name: $name) {{
    issue(number: $number) {{
      number title
      subIssues(first: 100) {{
        nodes {{{SUB_ISSUE_FIELDS}
        }}
      }}
    }}
  }}
}}"""

ISSUE_QUERY = f"""query($owner: String!, $name: String!, $number: Int!) {{
  repository(owner: $owner, name: $name) {{
    issue(number: $number) {{
      number title state url body
      labels(first: 20) {{ nodes {{ name }} }}
      assignees(first: 10) {{ nodes {{ login }} }}
      parent {{ number title body }}
      subIssuesSummary {{ total completed }}
      subIssues(first: 100) {{
        nodes {{{SUB_ISSUE_FIELDS}
        }}
      }}
      blockedBy(first: 20) {{ nodes {{ number state }} }}
      closedByPullRequestsReferences(first: 5, includeClosedPrs: true) {{ nodes {{ number state }} }}
      comments(last: 20) {{
        totalCount
        nodes {{ author {{ login }} createdAt body }}
      }}
    }}
  }}
}}"""


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], Result]


def run_process(argv: list[str]) -> Result:
    done = subprocess.run(argv, capture_output=True, text=True)
    return Result(done.returncode, done.stdout, done.stderr)


def parse_sub_issue(node: dict[str, Any]) -> SubIssue:
    return SubIssue(
        number=node["number"],
        title=node["title"],
        state=node["state"],
        assignees=tuple(a["login"] for a in node["assignees"]["nodes"]),
        open_blockers=node["issueDependenciesSummary"]["blockedBy"],
    )


def text(value: str | None) -> str:
    return (value or "").replace("\r\n", "\n")


def parse_issue(node: dict[str, Any]) -> Issue:
    parent = node["parent"] or {}
    return Issue(
        number=node["number"],
        title=node["title"],
        state=node["state"],
        url=node["url"],
        body=text(node["body"]),
        labels=tuple(label["name"] for label in node["labels"]["nodes"]),
        assignees=tuple(a["login"] for a in node["assignees"]["nodes"]),
        parent_number=parent.get("number"),
        parent_title=parent.get("title", ""),
        parent_body=text(parent.get("body")),
        sub_issues=tuple(parse_sub_issue(sub) for sub in node["subIssues"]["nodes"]),
        sub_issue_total=node["subIssuesSummary"]["total"],
        sub_issue_completed=node["subIssuesSummary"]["completed"],
        blockers=tuple(Link(b["number"], b["state"]) for b in node["blockedBy"]["nodes"]),
        pull_requests=tuple(Link(pr["number"], pr["state"]) for pr in node["closedByPullRequestsReferences"]["nodes"]),
        comments=tuple(
            Comment((c["author"] or {}).get("login", "ghost"), c["createdAt"][:10], text(c["body"]))
            for c in node["comments"]["nodes"]
        ),
        comment_total=node["comments"]["totalCount"],
    )


def parse_remote(url: str) -> str:
    match = REMOTE.search(url.strip()) if "://" in url or "@" in url else None
    if match is None:
        raise CliError(f"Cannot read OWNER/REPO from the origin URL {url.strip()!r}. Pass --repo OWNER/REPO.")
    return f"{match['owner']}/{match['name']}"


class GitHub:
    """The only place that runs gh or git. Every gh call names the repo."""

    def __init__(self, runner: Runner, repo: str | None = None) -> None:
        self.runner = runner
        self._repo = repo

    @property
    def repo(self) -> str:
        if self._repo is None:
            result = self._run(["git", "remote", "get-url", "origin"])
            if result.returncode != 0:
                raise CliError(f"Cannot read the origin remote: {result.stderr.strip()}. Pass --repo OWNER/REPO.")
            self._repo = parse_remote(result.stdout)
        return self._repo

    def graphql(self, query: str, **variables: int | str | None) -> dict[str, Any]:
        owner, name = self.repo.split("/")
        argv = ["gh", "api", "graphql", "-f", f"query={query}", "-f", f"owner={owner}", "-f", f"name={name}"]
        for key, value in variables.items():
            if value is not None:
                argv += ["-F" if isinstance(value, int) else "-f", f"{key}={value}"]
        return json.loads(self._gh(argv))["data"]

    def sub_issues(self, number: int) -> tuple[str, list[SubIssue]]:
        issue = self.graphql(FRONTIER_QUERY, number=number)["repository"]["issue"]
        return issue["title"], [parse_sub_issue(node) for node in issue["subIssues"]["nodes"]]

    def issue(self, number: int) -> Issue:
        return parse_issue(self.graphql(ISSUE_QUERY, number=number)["repository"]["issue"])

    def toplevel(self) -> str | None:
        result = self._run(["git", "rev-parse", "--show-toplevel"])
        return result.stdout.strip() if result.returncode == 0 else None

    def _gh(self, argv: list[str]) -> str:
        result = self._run(argv)
        if result.returncode == 4:
            raise CliError("gh is not signed in. Run `gh auth login`.")
        if result.returncode != 0:
            raise CliError(f"gh failed: {(result.stderr or result.stdout).strip()}")
        return result.stdout

    def _run(self, argv: list[str]) -> Result:
        try:
            return self.runner(argv)
        except FileNotFoundError:
            raise CliError(f"`{argv[0]}` is not on PATH.") from None
