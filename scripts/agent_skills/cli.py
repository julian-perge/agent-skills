import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path

from agent_skills import REFUSED, CliError, render, tracker
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


def branch_kind(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9-]*", value):
        raise argparse.ArgumentTypeError(f"expected a lowercase branch type such as feat or fix, got {value!r}")
    return value


def spec_files(root: Path) -> frozenset[str]:
    return frozenset(f"spec/{path.name}" for path in (root / "spec").glob("*.md"))


def checkout_root(gh: GitHub) -> Path:
    return Path(gh.toplevel() or ".")


def issue_verb(gh: GitHub, args: argparse.Namespace) -> str:
    issue = gh.issue(args.number)
    return render.issue_report(issue, tracker.spec_for(issue, spec_files(checkout_root(gh))), args.full)


def pr_parts(gh: GitHub, number: int) -> tuple[tracker.PullRequest, tracker.TaskMatch, str, tracker.SpecMatch, str | None]:
    pr = gh.pull_request(number)
    root = checkout_root(gh)
    task = tracker.pr_task(tuple(issue.number for issue in pr.closing), pr.body, pr.head)
    issue = next((issue for issue in pr.closing if issue.number == task.number), None)
    if issue is None and task.number is not None:
        issue = gh.task_issue(task.number)
    spec = tracker.spec_for(issue, spec_files(root)) if issue else tracker.SpecMatch(None, "none", guess=False)
    standard = tracker.standard_file(frozenset(name for name in tracker.STANDARD_FILES if (root / name).is_file()))
    return pr, task, issue.title if issue else "", spec, standard


def pr_verb(gh: GitHub, args: argparse.Namespace) -> str:
    pr, task, title, spec, standard = pr_parts(gh, args.number)
    return render.pr_report(pr, task, title, spec, standard, args.full)


def next_cmd_verb(gh: GitHub, args: argparse.Namespace) -> str:
    number = args.number
    if args.stage == "spec":
        return f"/agent-skills:spec #{number}\n"
    if args.stage == "build":
        _, subs = gh.sub_issues(number)
        result = tracker.frontier(subs)
        if result.number is None:
            raise CliError(f"No frontier for #{number}: {result.reason}.", REFUSED)
        return f"/agent-skills:build #{result.number}\n"
    if args.stage == "plan":
        spec = tracker.spec_for(gh.task_issue(number), spec_files(checkout_root(gh)))
        if spec.path is None:
            raise CliError(render.spec_problem(number, spec) + ".", REFUSED)
        if spec.guess:
            print(render.spec_guess_note(spec), file=sys.stderr)
        return f"/agent-skills:plan #{number}, spec {spec.path}\n"
    _, task, _, spec, standard = pr_parts(gh, number)
    for note in render.review_notes(task, spec, standard):
        print(note, file=sys.stderr)
    return render.review_line(number, task, spec, standard) + "\n"


def claim_verb(gh: GitHub, args: argparse.Namespace) -> str:
    issue, me = gh.claim_view(args.number)
    refusal = tracker.claim_refusal(issue, me)
    branch, default = None, ""
    if refusal is None and not args.no_branch:
        branch = tracker.branch_name(issue, args.type)
        if gh.tree_has_changes():
            refusal = "the working tree has changes. Commit or stash them, or pass --no-branch."
        else:
            default = gh.default_branch()
            if gh.branch_exists(branch):
                refusal = f"the branch {branch} already exists."
    if refusal:
        raise CliError(f"Not claimed: {refusal}", REFUSED)
    assigned = "skipped" if args.no_assign else "already" if me in issue.assignees else "now"
    if assigned == "now":
        gh.add_assignee_me(issue.number)
    commit = ""
    if branch:
        try:
            commit = gh.branch_from(branch, default)
        except CliError as error:
            done = f"#{issue.number} is assigned to @me, but the branch step failed. " if assigned == "now" else ""
            raise CliError(done + str(error)) from None
    return render.claim_report(issue.number, assigned, branch, default, commit)


def workflow_block(text: str) -> str | None:
    match = re.search(r"^## Workflow\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return match[1] if match else None


def preflight(root: Path) -> None:
    if not (root / "docs" / "agents" / "workflow.md").is_file():
        raise CliError("No docs/agents/workflow.md in this repo. Run /agent-skills:setup-workflow first.")
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = root / name
        block = workflow_block(path.read_text()) if path.is_file() else None
        if block is not None:
            if re.search(r"tracked in GitHub Issues", block, re.IGNORECASE):
                return
            raise CliError(f"The ## Workflow block of {name} does not say that tasks are tracked in GitHub Issues. `next` does not support files mode.")
    raise CliError("Neither AGENTS.md nor CLAUDE.md has a ## Workflow block that says tasks are tracked in GitHub Issues. `next` does not support files mode.")


def next_verb(gh: GitHub, args: argparse.Namespace) -> str:
    root = checkout_root(gh)
    preflight(root)
    specs = spec_files(root)
    issues, pulls = gh.open_tracker()
    bodies = {number: gh.sub_issue_bodies(number) for number in tracker.plan_candidates(pulls, issues, specs)}
    groups = tracker.group(pulls, issues, specs, bodies)
    standard = tracker.standard_file(frozenset(name for name in tracker.STANDARD_FILES if (root / name).is_file()))
    return render.next_report(gh.repo, groups, standard, tracker.next_step(groups))


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

    pr = verbs.add_parser("pr", help="one pull request with its task, spec, standard, files and the review line")
    pr.add_argument("number", type=issue_number, metavar="N")
    pr.add_argument("--full", action="store_true", help="print the whole body")
    pr.set_defaults(handler=pr_verb)

    next_verb_parser = verbs.add_parser("next", help="what to do next: PRs to review, tasks to build, issues to plan, spec or refine")
    next_verb_parser.set_defaults(handler=next_verb)

    next_cmd = verbs.add_parser("next-cmd", help="the one paste line that ends a stage")
    next_cmd.add_argument("stage", choices=("review", "build", "plan", "spec"))
    next_cmd.add_argument("number", type=issue_number, metavar="N", help="the PR for review, the parent for build, the issue for plan and spec")
    next_cmd.set_defaults(handler=next_cmd_verb)

    claim = verbs.add_parser("claim", help="assign an issue to @me and make its branch from the default branch")
    claim.add_argument("number", type=issue_number, metavar="N")
    claim.add_argument("--type", type=branch_kind, metavar="TYPE", help="branch type (default: fix for a bug label, else feat)")
    claim.add_argument("--no-branch", action="store_true", help="assign only, make no branch")
    claim.add_argument("--no-assign", action="store_true", help="make the branch only, assign no one")
    claim.set_defaults(handler=claim_verb)

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
