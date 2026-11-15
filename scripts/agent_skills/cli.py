import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path

from agent_skills import CliError, render, tracker
from agent_skills.github import GitHub, Runner, run_process

Handler = Callable[[GitHub, argparse.Namespace], str]


def repo_arg(value: str) -> str:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        raise argparse.ArgumentTypeError(f"expected OWNER/REPO, got {value!r}")
    return value


def issue_number(value: str) -> int:
    digits = value.removeprefix("#")
    if not digits.isdigit():
        raise argparse.ArgumentTypeError(f"expected an issue number, got {value!r}")
    return int(digits)


def spec_files(gh: GitHub) -> frozenset[str]:
    root = Path(gh.toplevel() or ".")
    return frozenset(f"spec/{path.name}" for path in (root / "spec").glob("*.md"))


def issue_verb(gh: GitHub, args: argparse.Namespace) -> str:
    issue = gh.issue(args.number)
    return render.issue_report(issue, tracker.spec_for(issue, spec_files(gh)), args.full)


def frontier_verb(gh: GitHub, args: argparse.Namespace) -> str:
    title, subs = gh.sub_issues(args.number)
    return render.frontier_report(args.number, title, subs, tracker.frontier(subs))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-skills",
        description="Tracker lookups for the /agent-skills workflow. Exit codes: 0 done, 1 refused, 2 usage or environment error.",
    )
    parser.add_argument("--repo", type=repo_arg, metavar="OWNER/REPO", help="GitHub repo (default: parsed from the origin remote)")
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="<verb>")

    issue = verbs.add_parser("issue", help="one issue with its parent, spec, blockers, pull requests, sub-issues and comments")
    issue.add_argument("number", type=issue_number, metavar="N")
    issue.add_argument("--full", action="store_true", help="print the whole body, every comment read and every sub-issue read")
    issue.set_defaults(handler=issue_verb)

    frontier = verbs.add_parser("frontier", help="the open sub-issues of P and the next one to build")
    frontier.add_argument("number", type=issue_number, metavar="P")
    frontier.set_defaults(handler=frontier_verb)
    return parser


def main(argv: list[str] | None = None, runner: Runner = run_process) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as stop:
        return int(stop.code or 0)
    handler: Handler = args.handler
    try:
        output = handler(GitHub(runner, args.repo), args)
    except CliError as error:
        print(error, file=sys.stderr)
        return error.code
    sys.stdout.write(output)
    return 0
