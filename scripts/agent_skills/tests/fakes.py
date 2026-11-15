import json
from pathlib import Path

from agent_skills.github import Result

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text()


def fixture_json(name: str) -> str:
    return json.dumps(json.loads(fixture_text(name)))


class FakeRunner:
    """Serves canned results for argv patterns and records every call.

    A rule matches when every one of its tokens is an item of the argv and
    the first token is the program name. Each rule answers once, in the
    order the rules were added, so a test can queue several pages for the
    same query. A call that no rule answers fails the test.
    """

    def __init__(self, missing: frozenset[str] = frozenset()) -> None:
        self.missing = missing
        self.rules: list[tuple[tuple[str, ...], Result]] = []
        self.calls: list[list[str]] = []

    def on(self, *tokens: str, stdout: str = "", stderr: str = "", returncode: int = 0) -> "FakeRunner":
        self.rules.append((tokens, Result(returncode, stdout, stderr)))
        return self

    def __call__(self, argv: list[str]) -> Result:
        self.calls.append(list(argv))
        if argv[0] in self.missing:
            raise FileNotFoundError(argv[0])
        for index, (tokens, result) in enumerate(self.rules):
            if argv[0] == tokens[0] and all(token in argv for token in tokens[1:]):
                del self.rules[index]
                return result
        raise AssertionError(f"no fake result for {argv}")

    def gh_calls(self) -> list[list[str]]:
        return [call for call in self.calls if call[0] == "gh"]

    def git_calls(self) -> list[list[str]]:
        return [call for call in self.calls if call[0] == "git"]


def names_repo(argv: list[str], repo: str) -> bool:
    owner, name = repo.split("/")
    if "--repo" in argv and argv[argv.index("--repo") + 1] == repo:
        return True
    if any(f"repos/{repo}/" in arg for arg in argv):
        return True
    return f"owner={owner}" in argv and f"name={name}" in argv


def with_origin(runner: FakeRunner, url: str = "git@github.com:julian-perge/agent-skills.git") -> FakeRunner:
    return runner.on("git", "remote", "get-url", "origin", stdout=url + "\n")
