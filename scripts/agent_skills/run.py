import argparse
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import TextIO

from agent_skills.github import GitHub

USAGE = 125
NOT_EXECUTABLE = 126
NOT_FOUND = 127
SUMMARY_LIMIT = 40
LABEL_LIMIT = 40

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")

# The table in spec/helpers-run-wrapper.md lists the runner each pattern comes from.
SUMMARY_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^(FAILED|ERROR) ",
        r"^E  ",
        r"=+ .*(passed|failed|error).* =+$",
        r"^\d+ [a-z]+(, \d+ [a-z]+)* in \d+(\.\d+)?s",
        r"^no tests ran in ",
        r"short test summary",
        r"Passing Tests",
        r"Failing Tests",
        r"Asserts",
        r"Risky",
        r"\[Failed\]",
        r"^- test_\w+",
        r"SCRIPT ERROR",
        r"Parse Error",
        r"\.+Failed$",
        r"- hook id:",
        r"- exit code:",
        r"Traceback \(most recent call last\)",
        r"^\w*Error:",
        r"^error(\[\w+\])?:",
        r"^fatal:",
    )
)


def clean(raw: str) -> str:
    return ANSI.sub("", raw.rstrip("\r\n")).rsplit("\r", 1)[-1]


def is_summary(line: str) -> bool:
    return any(pattern.search(line) for pattern in SUMMARY_PATTERNS)


class Digest:
    def __init__(self, tail: int) -> None:
        self.matches: list[str] = []
        self.seen: set[str] = set()
        self.last: deque[str] = deque(maxlen=tail)

    def add(self, line: str) -> None:
        self.last.append(line)
        if line not in self.seen and is_summary(line):
            self.seen.add(line)
            self.matches.append(line)

    def render(self) -> str:
        shown = self.matches[-SUMMARY_LIMIT:]
        count = f"{len(shown)}" if len(shown) == len(self.matches) else f"last {len(shown)} of {len(self.matches)}"
        parts = [f"## Summary lines ({count})", *shown, f"## Last {self.last.maxlen} lines", *self.last]
        return "\n".join(parts) + "\n"


def digest(lines: Iterable[str], tail: int = 15) -> Digest:
    result = Digest(tail)
    for line in lines:
        result.add(clean(line))
    return result


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:LABEL_LIMIT].strip("-")


def label(command: list[str], name: str | None) -> str:
    if name:
        return slug(name) or "run"
    words = [word for word in command if word != "env" and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", word)]
    return slug(" ".join(Path(word).name for word in words[:2])) or "run"


def open_log(command: list[str], name: str | None, gh: GitHub) -> tuple[Path, TextIO]:
    top = gh.toplevel()
    folder = Path(os.environ.get("TMPDIR") or "/tmp") / "agent-skills" / "runs" / (Path(top).name if top else "norepo")
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now():%Y%m%d-%H%M%S}-{label(command, name)}"
    for attempt in range(1, 100):
        path = folder / (f"{stem}.log" if attempt == 1 else f"{stem}-{attempt}.log")
        try:
            return path, path.open("x", encoding="utf-8")
        except FileExistsError:
            continue
    raise FileExistsError(f"no free log name for {stem} in {folder}")


def exit_code(returncode: int) -> int:
    return 128 - returncode if returncode < 0 else returncode


def run_command(command: list[str], name: str | None, tail: int, gh: GitHub, out: TextIO) -> int:
    path, log = open_log(command, name, gh)
    print(f"log: {path}", file=out, flush=True)
    result = Digest(tail)
    start = time.monotonic()
    with log:
        try:
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except (FileNotFoundError, PermissionError) as error:
            missing = isinstance(error, FileNotFoundError)
            message = f"agent-skills run: {'command not found' if missing else 'not executable'}: {command[0]}"
            print(message, file=sys.stderr)
            log.write(message + "\n")
            code = NOT_FOUND if missing else NOT_EXECUTABLE
        else:
            def forward(signum: int, frame: object) -> None:
                child.send_signal(signum)

            # Python accepts signal handlers only in the main thread, so a run started from another thread does not forward signals.
            in_main = threading.current_thread() is threading.main_thread()
            previous = {signum: signal.signal(signum, forward) for signum in (signal.SIGINT, signal.SIGTERM)} if in_main else {}
            try:
                assert child.stdout is not None
                with child.stdout:
                    for raw in child.stdout:
                        line = clean(raw.decode("utf-8", errors="replace"))
                        log.write(line + "\n")
                        log.flush()
                        result.add(line)
                code = exit_code(child.wait())
            finally:
                for signum, handler in previous.items():
                    signal.signal(signum, handler)
    out.write(f"exit {code} after {time.monotonic() - start:.1f}s: {shlex.join(command)}\n")
    out.write(result.render())
    out.flush()
    return code


def tail_count(value: str) -> int:
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError(f"expected a positive number of lines, got {value!r}")
    return int(value)


def add_parser(verbs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = verbs.add_parser(
        "run",
        help="run a test, lint or build command once, keep the full log and print a short summary",
        description="Runs CMD without a shell, saves its output to a log file and prints the log path, the exit code, "
        "the summary lines and the last lines. Exits with the command's own code, 125 on a usage error, "
        "127 when the command is not found and 128 plus the signal number when a signal ends it.",
    )
    parser.add_argument("--name", metavar="LABEL", help="label for the log file name (default: the first two words of CMD)")
    parser.add_argument("--tail", type=tail_count, default=15, metavar="N", help="how many last lines to print (default: 15)")
    parser.add_argument("command", nargs=argparse.REMAINDER, metavar="-- CMD [ARG...]")

    def usage_error(message: str) -> None:
        parser.print_usage(sys.stderr)
        parser.exit(USAGE, f"agent-skills run: error: {message}\n")

    parser.error = usage_error  # type: ignore[method-assign]
    return parser


def run_verb(gh: GitHub, args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given. Put it after --, for example: agent-skills run -- uv run pytest -q")
    return run_command(command, args.name, args.tail, gh, sys.stdout)
