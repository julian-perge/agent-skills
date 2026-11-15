import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from agent_skills import CliError

REMOTE = re.compile(r"[/:](?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], Result]


def run_process(argv: list[str]) -> Result:
    done = subprocess.run(argv, capture_output=True, text=True)
    return Result(done.returncode, done.stdout, done.stderr)


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
