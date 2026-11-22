import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from agent_skills.github import Result
from fakes import FakeRunner

URL = "https://github.com/julian-perge/urchin.git"
# No user or system git config, so a hook, a signing key or an alias of the machine cannot change a test.
ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "protocol.file.allow=always", *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}: {done.stderr}")
    return done.stdout.strip()


def commit(cwd: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        path = cwd / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(cwd, "add", "-A")
    git(cwd, "commit", "-q", "-m", message)
    return git(cwd, "rev-parse", "HEAD")


def clone(origin: Path, target: Path) -> Path:
    """A clone whose origin URL names GitHub, as a real checkout does, while git reads and writes the local bare repo."""
    git(origin.parent, "clone", "-q", str(origin), str(target))
    git(target, "config", "remote.origin.url", URL)
    git(target, "config", f"url.{origin}.insteadOf", URL)
    return target


def new_origin(folder: Path, files: dict[str, str]) -> tuple[Path, Path]:
    """A bare repo with one commit on main, and a clone of it."""
    origin = folder / "origin.git"
    git(folder, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = folder / "seed"
    git(folder, "init", "-q", "-b", "main", str(seed))
    commit(seed, files, "first")
    git(seed, "push", "-q", str(origin), "main")
    return origin, clone(origin, folder / "work")


class RealGit:
    """Runs git for real and answers gh from canned results, so a test can look at the repos afterwards."""

    def __init__(self, on_merge: Callable[[], None] | None = None) -> None:
        self.gh = FakeRunner()
        self.on_merge = on_merge
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> Result:
        self.calls.append(list(argv))
        if argv[0] != "gh":
            done = subprocess.run(argv, capture_output=True, text=True)
            return Result(done.returncode, done.stdout, done.stderr)
        if argv[:3] == ["gh", "pr", "merge"] and self.on_merge:
            self.on_merge()
        return self.gh(argv)

    def gh_calls(self) -> list[list[str]]:
        return [call for call in self.calls if call[0] == "gh"]
