import json
import re
import subprocess
from dataclasses import dataclass
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from agent_skills import CliError
from agent_skills.land import LandPull
from agent_skills.tracker import Comment, FileChange, Issue, Link, OpenPull, PullRequest, Review, SubIssue, TrackerIssue

REMOTE = re.compile(r"[/:](?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?/?$")

SUB_ISSUE_FIELDS = """
        number title state
        labels(first: 20) { nodes { name } }
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

BODY_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { issue(number: $number) { body } }
}"""

ISSUE_QUERY = f"""query($owner: String!, $name: String!, $number: Int!) {{
  repository(owner: $owner, name: $name) {{
    issue(number: $number) {{
      number title state url body
      labels(first: 20) {{ nodes {{ name }} }}
      assignees(first: 10) {{ nodes {{ login }} }}
      parent {{
        number title body
        comments(last: 20) {{ nodes {{ author {{ login }} createdAt body }} }}
      }}
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

TASK_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) { number title body parent { number title body } }
  }
}"""

CLAIM_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  viewer { login }
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      number title state
      labels(first: 20) { nodes { name } }
      assignees(first: 10) { nodes { login } }
      blockedBy(first: 20) { nodes { number state } }
    }
  }
}"""

NEXT_QUERY = """query($owner: String!, $name: String!, $after: String, $pulls: Boolean!) {
  repository(owner: $owner, name: $name) {
    issues(states: OPEN, first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body
        assignees(first: 1) { totalCount }
        labels(first: 20) { nodes { name } }
        parent { number body }
        subIssuesSummary { total }
        issueDependenciesSummary { blockedBy }
        closedByPullRequestsReferences(first: 5, includeClosedPrs: false) { nodes { number } }
      }
    }
    pullRequests(states: OPEN, first: 100) @include(if: $pulls) {
      nodes { number title headRefName body isDraft createdAt }
    }
  }
}"""

SUB_ISSUE_BODIES_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) { subIssues(first: 100) { nodes { body } } }
  }
}"""

PR_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number title state isDraft url body baseRefName headRefName
      closingIssuesReferences(first: 5) {
        nodes { number title body parent { number title body } }
      }
      files(first: 100) {
        totalCount
        nodes { path additions deletions }
      }
      commits(last: 20) {
        totalCount
        nodes { commit { messageHeadline } }
      }
      lastCommit: commits(last: 1) {
        nodes { commit { statusCheckRollup { state } } }
      }
      reviews(last: 5) {
        nodes { author { login } state submittedAt }
      }
    }
  }
}"""


LAND_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number title state isDraft url body baseRefName headRefName headRefOid mergeable
      files(first: 100) {
        totalCount
        nodes { path }
      }
      comments(last: 50) { nodes { body createdAt } }
      closingIssuesReferences(first: 50) {
        nodes {
          comments(last: 50) { nodes { body createdAt } }
          parent { comments(last: 50) { nodes { body createdAt } } }
        }
      }
    }
  }
}"""


PULL_BODY_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { pullRequest(number: $number) { body } }
}"""


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], Result]


def run_process(argv: list[str]) -> Result:
    done = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return Result(done.returncode, done.stdout, done.stderr)


def parse_sub_issue(node: dict[str, Any]) -> SubIssue:
    return SubIssue(
        number=node["number"],
        title=node["title"],
        state=node["state"],
        assignees=tuple(a["login"] for a in node["assignees"]["nodes"]),
        open_blockers=node["issueDependenciesSummary"]["blockedBy"],
        labels=tuple(label["name"] for label in node["labels"]["nodes"]),
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
        comments=tuple(parse_comment(c) for c in node["comments"]["nodes"]),
        comment_total=node["comments"]["totalCount"],
        parent_comments=tuple(parse_comment(c) for c in (parent.get("comments") or {}).get("nodes", [])),
    )


def parse_comment(node: dict[str, Any]) -> Comment:
    return Comment((node["author"] or {}).get("login", "ghost"), node["createdAt"][:10], text(node["body"]), node["createdAt"])


def parse_closing_issue(node: dict[str, Any]) -> Issue:
    parent = node["parent"] or {}
    return Issue(
        number=node["number"],
        title=node["title"],
        body=text(node["body"]),
        parent_number=parent.get("number"),
        parent_title=parent.get("title", ""),
        parent_body=text(parent.get("body")),
    )


def parse_pull_request(node: dict[str, Any]) -> PullRequest:
    last = node["lastCommit"]["nodes"]
    rollup = last[0]["commit"]["statusCheckRollup"] if last else None
    return PullRequest(
        number=node["number"],
        title=node["title"],
        state=node["state"],
        draft=node["isDraft"],
        url=node["url"],
        body=text(node["body"]),
        base=node["baseRefName"],
        head=node["headRefName"],
        closing=tuple(parse_closing_issue(issue) for issue in node["closingIssuesReferences"]["nodes"]),
        files=tuple(FileChange(f["path"], f["additions"], f["deletions"]) for f in node["files"]["nodes"]),
        file_total=node["files"]["totalCount"],
        commits=tuple(c["commit"]["messageHeadline"] for c in node["commits"]["nodes"]),
        commit_total=node["commits"]["totalCount"],
        checks=rollup["state"] if rollup else "none",
        reviews=tuple(
            Review((r["author"] or {}).get("login", "ghost"), r["state"], (r["submittedAt"] or "")[:10])
            for r in node["reviews"]["nodes"]
        ),
    )


def parse_land_pull(node: dict[str, Any], paths: tuple[str, ...]) -> LandPull:
    """The body stays exactly as GitHub stores it, because `evidence --add` writes it back. The comments of all threads are oldest first."""
    threads = [node["comments"]]
    for issue in node["closingIssuesReferences"]["nodes"]:
        threads += [issue["comments"], (issue["parent"] or {}).get("comments") or {"nodes": []}]
    comments = sorted((comment for thread in threads for comment in thread["nodes"]), key=lambda comment: comment["createdAt"])
    return LandPull(
        number=node["number"],
        title=node["title"],
        state=node["state"],
        draft=node["isDraft"],
        url=node["url"],
        body=node["body"] or "",
        base=node["baseRefName"],
        head=node["headRefName"],
        head_commit=node["headRefOid"],
        mergeable=node["mergeable"],
        paths=paths,
        comments=tuple(text(comment["body"]) for comment in comments),
    )


def parse_worktrees(porcelain: str) -> list[tuple[str, str | None]]:
    """Each worktree of `git worktree list --porcelain` as its path and its branch. The main worktree is first."""
    trees: list[tuple[str, str | None]] = []
    for block in porcelain.strip().split("\n\n"):
        fields = dict(line.partition(" ")[::2] for line in block.splitlines())
        if "worktree" in fields:
            trees.append((fields["worktree"], fields["branch"].removeprefix("refs/heads/") if "branch" in fields else None))
    return trees


def parse_claim_issue(node: dict[str, Any]) -> Issue:
    return Issue(
        number=node["number"],
        title=node["title"],
        state=node["state"],
        labels=tuple(label["name"] for label in node["labels"]["nodes"]),
        assignees=tuple(a["login"] for a in node["assignees"]["nodes"]),
        blockers=tuple(Link(b["number"], b["state"]) for b in node["blockedBy"]["nodes"]),
    )


def parse_tracker_issue(node: dict[str, Any]) -> TrackerIssue:
    parent = node["parent"] or {}
    return TrackerIssue(
        number=node["number"],
        title=node["title"],
        body=text(node["body"]),
        labels=tuple(label["name"] for label in node["labels"]["nodes"]),
        assigned=node["assignees"]["totalCount"] > 0,
        parent_number=parent.get("number"),
        parent_body=text(parent.get("body")),
        sub_issue_total=node["subIssuesSummary"]["total"],
        open_blockers=node["issueDependenciesSummary"]["blockedBy"],
        open_pull_requests=tuple(pr["number"] for pr in node["closedByPullRequestsReferences"]["nodes"]),
    )


def parse_open_pull(node: dict[str, Any]) -> OpenPull:
    return OpenPull(node["number"], node["title"], node["headRefName"], text(node["body"]), node["isDraft"], node["createdAt"])


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

    def graphql(self, query: str, **variables: bool | int | str | None) -> dict[str, Any]:
        owner, name = self.repo.split("/")
        argv = ["gh", "api", "graphql", "-f", f"query={query}", "-f", f"owner={owner}", "-f", f"name={name}"]
        for key, value in variables.items():
            if isinstance(value, bool):
                argv += ["-F", f"{key}={str(value).lower()}"]
            elif value is not None:
                argv += ["-F" if isinstance(value, int) else "-f", f"{key}={value}"]
        return json.loads(self._gh(argv))["data"]

    def sub_issues(self, number: int) -> tuple[str, list[SubIssue]]:
        issue = self.graphql(FRONTIER_QUERY, number=number)["repository"]["issue"]
        return issue["title"], [parse_sub_issue(node) for node in issue["subIssues"]["nodes"]]

    def issue(self, number: int) -> Issue:
        return parse_issue(self.graphql(ISSUE_QUERY, number=number)["repository"]["issue"])

    def pull_request(self, number: int) -> PullRequest:
        return parse_pull_request(self.graphql(PR_QUERY, number=number)["repository"]["pullRequest"])

    def task_issue(self, number: int) -> Issue:
        return parse_closing_issue(self.graphql(TASK_QUERY, number=number)["repository"]["issue"])

    def claim_view(self, number: int) -> tuple[Issue, str]:
        data = self.graphql(CLAIM_QUERY, number=number)
        return parse_claim_issue(data["repository"]["issue"]), data["viewer"]["login"]

    def issue_body(self, number: int) -> str:
        """The body exactly as GitHub stores it, line ends included, so a write changes nothing else."""
        return self.graphql(BODY_QUERY, number=number)["repository"]["issue"]["body"] or ""

    def edit_body(self, number: int, body: str) -> None:
        self._gh(["gh", "issue", "edit", str(number), "--repo", self.repo, "--body", body])

    def comment(self, number: int, body: str) -> str:
        return self._gh(["gh", "issue", "comment", str(number), "--repo", self.repo, "--body", body])

    def add_assignee_me(self, number: int) -> None:
        self._gh(["gh", "issue", "edit", str(number), "--repo", self.repo, "--add-assignee", "@me"])

    def land_pull(self, number: int) -> LandPull:
        node = self.graphql(LAND_QUERY, number=number)["repository"]["pullRequest"]
        paths = tuple(file["path"] for file in node["files"]["nodes"])
        if node["files"]["totalCount"] > len(paths):
            listing = self._gh(["gh", "api", "--paginate", f"repos/{self.repo}/pulls/{number}/files", "--jq", ".[].filename"])
            paths = tuple(listing.splitlines())
        return parse_land_pull(node, paths)

    def pull_head(self, number: int) -> str:
        return self._gh(["gh", "pr", "view", str(number), "--repo", self.repo, "--json", "headRefOid", "--jq", ".headRefOid"]).strip()

    def pull_body(self, number: int) -> str:
        return self.graphql(PULL_BODY_QUERY, number=number)["repository"]["pullRequest"]["body"] or ""

    def pull_state(self, number: int) -> str:
        return self._gh(["gh", "pr", "view", str(number), "--repo", self.repo, "--json", "state", "--jq", ".state"]).strip()

    def origin_repo(self) -> str:
        return parse_remote(self._git(["git", "config", "--get", "remote.origin.url"]))

    def file_at(self, ref: str, path: str) -> str | None:
        """The text of a file at a git ref, or None when the ref has no such file."""
        result = self._run(["git", "show", f"{ref}:{path}"])
        return result.stdout if result.returncode == 0 else None

    def edit_pull_body(self, number: int, body: str) -> None:
        self._gh(["gh", "api", "--method", "PATCH", f"repos/{self.repo}/pulls/{number}", "-f", f"body={body}", "--silent"])

    def push_files(self, branch: str, folder: str, files: Sequence[Path], message: str, index: Path) -> str:
        """Adds the files to `folder` on `branch` of origin as one new commit, and returns the commit.

        It builds the commit in the scratch index file `index`, so the checkout and its own index stay as they are.
        """
        scratch = ["env", f"GIT_INDEX_FILE={index}", "git"]
        ref = f"refs/heads/{branch}"
        parent = self._git(["git", "ls-remote", "origin", ref]).split()[:1]
        if parent:
            self._git(["git", "fetch", "origin", ref])
            self._git([*scratch, "read-tree", parent[0]])
        for file in files:
            blob = self._git(["git", "hash-object", "-w", "--no-filters", "--", str(file)]).strip()
            self._git([*scratch, "update-index", "--add", "--cacheinfo", f"100644,{blob},{folder}/{file.name}"])
        tree = self._git([*scratch, "write-tree"]).strip()
        commit = self._git(["git", "commit-tree", tree, *(["-p", parent[0]] if parent else []), "-m", message]).strip()
        # The push is not forced, so a push from another session in the meantime makes this one fail and keeps theirs.
        self._git(["git", "push", "--no-verify", "origin", f"{commit}:{ref}"])
        return commit

    def commits_behind(self, base: str) -> int:
        """How many commits of origin/<base> the checkout lacks. Fetch the base branch first."""
        return int(self._git(["git", "rev-list", "--count", f"HEAD..origin/{base}"]).strip())

    def current_branch(self) -> str:
        return self._git(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()

    def head_commit(self) -> str:
        return self._git(["git", "rev-parse", "HEAD"]).strip()

    def short_head(self, checkout: str) -> str:
        return self._git(["git", "-C", checkout, "rev-parse", "--short", "HEAD"]).strip()

    def branch_commit(self, checkout: str, branch: str) -> str:
        return self._git(["git", "-C", checkout, "rev-parse", f"refs/heads/{branch}"]).strip()

    def status(self, checkout: str) -> list[str]:
        """Every changed, untracked and ignored path of a checkout, and each submodule that has one, whatever the git config says to hide."""
        return self._git(["git", "-C", checkout, "status", "--porcelain", "--ignored", "--untracked-files=normal", "--ignore-submodules=none"]).splitlines()

    def unpushed_in_submodules(self, checkout: str) -> list[str]:
        """One commit per submodule that holds a commit, a branch or a stash that none of its remotes has.

        A linked worktree keeps the git folders of its submodules inside itself, so such a commit goes away with the worktree.
        """
        listing = self._git(["git", "-C", checkout, "submodule", "foreach", "--quiet", "--recursive", "git rev-list -n 1 --all --not --remotes"])
        return listing.split()

    def has_ref(self, checkout: str, ref: str) -> bool:
        return self._run(["git", "-C", checkout, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]).returncode == 0

    def get_commit(self, checkout: str, commit: str) -> bool:
        """Whether the clone has the commit, after a fetch of that one commit from origin when it lacks it."""
        if self.has_ref(checkout, commit):
            return True
        return self._run(["git", "-C", checkout, "fetch", "--quiet", "origin", commit]).returncode == 0 and self.has_ref(checkout, commit)

    def patch_id(self, checkout: str, base_ref: str, commit: str, paths: Sequence[str] = ()) -> str:
        """The verbatim patch-id of the change that `commit` makes on top of its merge base with `base_ref`, or "" when that change is empty.

        When `paths` is given, only the change to those git pathspecs counts.
        """
        fork = self._git(["git", "-C", checkout, "merge-base", base_ref, commit]).strip()
        # The runner starts each command without a shell, and git patch-id reads its input only from stdin, so a short sh script joins the two commands.
        # The script stops when git diff fails, so a failed diff cannot give the patch-id of an empty change.
        script = 'checkout=$1 fork=$2 commit=$3; shift 3; change=$(git -C "$checkout" diff --no-color --no-ext-diff "$fork" "$commit" "$@") && printf "%s\\n" "$change" | git -C "$checkout" patch-id --verbatim'
        pathspecs = ["--", *paths] if paths else []
        return (self._git(["sh", "-c", script, "sh", checkout, fork, commit, *pathspecs]).split() or [""])[0]

    def commits_ahead(self, checkout: str, branch: str, merged: str) -> int:
        """How many commits the local branch has that neither origin/<branch> nor the commit `merged` holds, or 0 when the checkout has no such local branch."""
        if not self.has_ref(checkout, f"refs/heads/{branch}"):
            return 0
        return int(self._git(["git", "-C", checkout, "rev-list", "--count", f"refs/heads/{branch}", "--not", f"origin/{branch}", merged]).strip())

    def worktrees(self) -> list[tuple[str, str | None]]:
        return parse_worktrees(self._git(["git", "worktree", "list", "--porcelain"]))

    def merge(self, number: int, method: str, commit: str) -> None:
        self._gh(["gh", "pr", "merge", str(number), "--repo", self.repo, f"--{method}", "--delete-branch", "--match-head-commit", commit])

    def switch(self, branch: str) -> None:
        self._git(["git", "switch", branch])

    def fetch(self, checkout: str) -> None:
        """Fetches origin and drops the remote-tracking refs of branches that origin deleted, such as a merged PR branch."""
        self._git(["git", "-C", checkout, "fetch", "--prune", "origin"])

    def fast_forward(self, checkout: str, branch: str) -> None:
        self._git(["git", "-C", checkout, "merge", "--ff-only", f"origin/{branch}"])

    def remove_worktree(self, main: str, path: str) -> None:
        # Git refuses to remove a worktree that has a submodule without --force. The caller checks first that the worktree has no changed or untracked file.
        self._git(["git", "-C", main, "worktree", "remove", "--force", path])

    def delete_branch(self, checkout: str, branch: str) -> None:
        # -D, because -d refuses when this checkout is not on the base branch. The caller checks first that the branch is at the merged commit.
        self._git(["git", "-C", checkout, "branch", "-D", branch])

    def tree_has_changes(self, checkout: str | None = None) -> bool:
        return bool(self._git(["git", *(["-C", checkout] if checkout else []), "status", "--porcelain", "--untracked-files=no", "--ignore-submodules=untracked"]).strip())

    def origin_url(self) -> str | None:
        """The origin URL as the git config holds it, before any insteadOf rewrite, or None when the repo has no origin remote."""
        result = self._run(["git", "config", "--get", "remote.origin.url"])
        return result.stdout.strip() if result.returncode == 0 else None

    def commits_missing(self, ref: str) -> int:
        """How many commits of `ref` HEAD lacks."""
        return int(self._git(["git", "rev-list", "--count", f"HEAD..{ref}"]).strip())

    def changed_paths(self, *revisions: str) -> list[str]:
        return self._git(["git", "diff", "--name-only", "--no-renames", *revisions]).splitlines()

    def commit_path(self, checkout: str, path: str, message: str) -> str:
        """Commits only `path`, whatever else the index holds, and returns the new commit."""
        self._git(["git", "-C", checkout, "add", "--", path])
        self._git(["git", "-C", checkout, "commit", "--quiet", "-m", message, "--", path])
        return self._git(["git", "-C", checkout, "rev-parse", "HEAD"]).strip()

    def merge_no_ff(self, checkout: str, branch: str) -> Result:
        return self._run(["git", "-C", checkout, "merge", "--no-ff", "--no-edit", branch])

    def abort_merge(self, checkout: str) -> None:
        # A merge that git refused before it started leaves nothing to abort, and then git merge --abort fails, which is fine.
        self._run(["git", "-C", checkout, "merge", "--abort"])

    def delete_merged_branch(self, checkout: str, branch: str, base: str) -> None:
        """Deletes `branch` when `base` holds all of it. git branch -d is not enough: it refuses a branch whose upstream lacks the merge."""
        if self._run(["git", "-C", checkout, "merge-base", "--is-ancestor", f"refs/heads/{branch}", f"refs/heads/{base}"]).returncode != 0:
            raise CliError(f"{base} does not hold every commit of {branch}, so the branch stays.")
        self._git(["git", "-C", checkout, "branch", "-D", branch])

    def default_branch(self) -> str:
        result = self._run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
        if result.returncode != 0:
            raise CliError("Cannot read the default branch of origin. Run `git remote set-head origin --auto`.")
        return result.stdout.strip().removeprefix("refs/remotes/origin/")

    def branch_exists(self, branch: str) -> bool:
        refs = self._git(["git", "for-each-ref", "--format=%(refname)", f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"])
        return bool(refs.strip())

    def subjects_since(self, default: str) -> list[str]:
        return self._git(["git", "log", "--format=%s", f"origin/{default}..HEAD"]).splitlines()

    def branch_from(self, branch: str, default: str) -> str:
        self._git(["git", "fetch", "origin", default])
        self._git(["git", "switch", "-c", branch, f"origin/{default}"])
        return self._git(["git", "rev-parse", "--short", "HEAD"]).strip()

    def open_tracker(self) -> tuple[list[TrackerIssue], list[OpenPull]]:
        issues: list[TrackerIssue] = []
        pulls: list[OpenPull] = []
        after = None
        while True:
            repository = self.graphql(NEXT_QUERY, after=after, pulls=after is None)["repository"]
            issues += [parse_tracker_issue(node) for node in repository["issues"]["nodes"]]
            if "pullRequests" in repository:
                pulls = [parse_open_pull(node) for node in repository["pullRequests"]["nodes"]]
            page = repository["issues"]["pageInfo"]
            if not page["hasNextPage"]:
                return issues, pulls
            after = page["endCursor"]

    def sub_issue_bodies(self, number: int) -> tuple[str, ...]:
        issue = self.graphql(SUB_ISSUE_BODIES_QUERY, number=number)["repository"]["issue"]
        return tuple(text(node["body"]) for node in issue["subIssues"]["nodes"])

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

    def _git(self, argv: list[str]) -> str:
        result = self._run(argv)
        if result.returncode != 0:
            raise CliError(f"`{' '.join(argv)}` failed: {(result.stderr or result.stdout).strip()}")
        return result.stdout

    def _run(self, argv: list[str]) -> Result:
        try:
            return self.runner(argv)
        except FileNotFoundError:
            raise CliError(f"`{argv[0]}` is not on PATH.") from None
