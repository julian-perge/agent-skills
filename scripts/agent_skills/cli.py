import argparse
import re
import shlex
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from agent_skills import REFUSED, CliError, brief, land, render, run, tracker
from agent_skills.github import GitHub, Runner, run_process

Handler = Callable[[GitHub, argparse.Namespace], str]
GATE_FILE = "docs/agents/workflow.md"
MERGEABLE_READS = 5


def repo_arg(value: str) -> str:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        raise argparse.ArgumentTypeError(f"expected OWNER/REPO, got {value!r}")
    return value


def issue_number(value: str) -> int:
    digits = value.removeprefix("#")
    if not digits.isdigit():
        raise argparse.ArgumentTypeError(f"expected an issue number, got {value!r}")
    return int(digits)


def stage_arg(value: str) -> str:
    try:
        return brief.stage_name(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def branch_kind(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9-]*", value):
        raise argparse.ArgumentTypeError(f"expected a lowercase branch type such as feat or fix, got {value!r}")
    return value


def box_list(value: str) -> list[int]:
    parts = [part.strip() for part in value.split(",")]
    if not all(part.isdigit() for part in parts):
        raise argparse.ArgumentTypeError(f"expected box numbers such as 1,3, got {value!r}")
    return [int(part) for part in parts]


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


def workflow_text(root: Path) -> str:
    path = root / GATE_FILE
    if not path.is_file():
        raise CliError("No docs/agents/workflow.md in this repo. Run /agent-skills:setup-workflow first.")
    return path.read_text()


def brief_verb(gh: GitHub, args: argparse.Namespace) -> str:
    rules = f"# Rules for {args.stage}, from docs/agents/workflow.md\n\n{brief.RULES_NOTE}\n\n" + "".join(brief.stage_sections(workflow_text(checkout_root(gh)), args.stage))
    if args.number is None:
        return rules
    if args.stage != "review":
        return rules + brief_issue(gh, args.number, f"# Issue #{args.number}\n", args.full)
    pr, task, title, spec, standard = pr_parts(gh, args.number)
    task_part = brief_issue(gh, task.number, f"# Task #{task.number}\n", args.full) if task.number is not None else ""
    report = render.pr_report(pr, task, title, spec, standard, args.full)
    return rules + task_part + f"# PR #{args.number}\n" + report.split("\n", 1)[1]


def brief_issue(gh: GitHub, number: int, heading: str, full: bool) -> str:
    issue = gh.issue(number)
    spec = tracker.spec_for(issue, spec_files(checkout_root(gh)))
    report = render.issue_report(issue, spec, full, render.BRIEF_BODY_LIMIT, render.BRIEF_COMMENTS_SHOWN, render.BRIEF_COMMENT_LIMIT)
    return heading + report.split("\n", 1)[1]


def next_cmd_verb(gh: GitHub, args: argparse.Namespace) -> str:
    number = args.number
    if args.stage == "spec":
        return f"/agent-skills:spec #{number}\n"
    if args.stage == "build":
        _, subs = gh.sub_issues(number)
        result = tracker.frontier(subs)
        if result.number is None:
            raise CliError(f"No frontier for #{number}: {result.reason}.", REFUSED)
        return f"/agent-skills:build #{number if args.whole else result.number}\n"
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
    on_branch = tracker.task_refs(gh.subjects_since(gh.default_branch())) if args.auto else None
    refusal = tracker.claim_refusal(issue, me, on_branch)
    branch, default = None, ""
    if refusal is None and not args.no_branch and not args.auto:
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


def ac_verb(gh: GitHub, args: argparse.Namespace) -> str:
    body = gh.issue_body(args.number)
    boxes = tracker.ac_boxes(body)
    if boxes is None:
        raise CliError(f"#{args.number} has no Acceptance criteria heading.", REFUSED)
    if not boxes:
        raise CliError(f"#{args.number} has no checkbox under its Acceptance criteria heading.", REFUSED)
    if args.tick is None:
        return render.ac_report(boxes)
    wrong = [index for index in args.tick if not 1 <= index <= len(boxes)]
    if wrong:
        raise CliError(f"Not ticked: #{args.number} has boxes 1 to {len(boxes)}, not {', '.join(map(str, wrong))}.", REFUSED)
    ticked = tracker.tick_boxes(body, boxes, args.tick)
    if ticked == body:
        return render.ac_report(boxes)
    if gh.issue_body(args.number) != body:
        raise CliError(f"Not ticked: the body of #{args.number} changed while this ran. Run the command again.", REFUSED)
    gh.edit_body(args.number, ticked)
    return render.ac_report(tracker.ac_boxes(ticked))


def decide_verb(gh: GitHub, args: argparse.Namespace) -> str:
    body = sys.stdin.read().strip()
    if not body:
        raise CliError("Nothing posted: the decisions come on stdin, and stdin was empty.", REFUSED)
    target = f"PR #{args.pr}" if args.pr is not None else f"#{args.number}"
    header = f"### Decisions from the {args.stage} of {target}"
    first, _, rest = body.partition("\n")
    if first.strip() == header:
        body = rest.strip()
    return gh.comment(args.number, f"{header}\n\n{body}").strip() + "\n"


def gate_rules(gh: GitHub, root: Path, pull: land.LandPull) -> str:
    """The text of docs/agents/workflow.md that judges a pull request.

    It comes from the base branch, so a pull request cannot weaken its own gate. When the base branch has no such
    file yet, it comes from the checkout. Each of the two cases that can surprise prints a note to stderr.
    """
    gh.fetch(str(root))
    if not gh.has_ref(str(root), f"origin/{pull.base}"):
        raise CliError(f"This clone has no origin/{pull.base}, so the gate of the base branch cannot be read. Run `git fetch origin {pull.base}:refs/remotes/origin/{pull.base}`, then run the command again.")
    text = gh.file_at(f"origin/{pull.base}", GATE_FILE)
    if text is None:
        text = workflow_text(root)
        print(f"Note: {pull.base} has no {GATE_FILE} yet, so the gate comes from this checkout.", file=sys.stderr)
    elif GATE_FILE in pull.paths:
        print(f"Note: this pull request changes {GATE_FILE}. The gate comes from {pull.base}.", file=sys.stderr)
    problems = land.workflow_problems(text)
    if problems:
        raise CliError("\n".join([f"{GATE_FILE} has list items that cannot be read:", *(f"- {problem}" for problem in problems)]))
    return text


def evidence_verb(gh: GitHub, args: argparse.Namespace) -> str:
    pull = gh.land_pull(args.number)
    if args.add:
        return add_evidence(gh, pull, args.add)
    found = land.evidence(gate_rules(gh, checkout_root(gh), pull), pull.paths, pull.body)
    if found.missing:
        raise CliError(f"PR #{pull.number} needs evidence: {land.evidence_gap(pull.number, found)}", REFUSED)
    return render.evidence_report(pull.number, found)


def add_evidence(gh: GitHub, pull: land.LandPull, files: list[Path]) -> str:
    names = [file.name for file in files]
    problems = [f"{file} is not a file" for file in files if not file.is_file()]
    problems += [f"{file.name} is not an image ({', '.join(land.IMAGE_SUFFIXES)})" for file in files if file.suffix.lower() not in land.IMAGE_SUFFIXES]
    problems += [f"two files are named {name}" for name in sorted({name for name in names if names.count(name) > 1})]
    if not problems and gh.origin_repo().lower() != gh.repo.lower():
        problems = [f"the images would go to origin ({gh.origin_repo()}) and the links to {gh.repo}"]
    if problems:
        raise CliError(f"Nothing added: {'; '.join(problems)}.", REFUSED)
    folder = f"pr-{pull.number}"
    with tempfile.TemporaryDirectory() as scratch:
        commit = gh.push_files(land.EVIDENCE_BRANCH, folder, files, f"Evidence for PR #{pull.number}", Path(scratch) / "index")
    images = [(file.stem, land.image_url(gh.repo, commit, folder, file.name)) for file in files]
    if gh.pull_body(pull.number) != pull.body:
        raise CliError(
            f"The images are on the {land.EVIDENCE_BRANCH} branch at {commit[:8]}, but the body of PR #{pull.number} changed while this ran, so it was not edited. Run the command again.",
            REFUSED,
        )
    gh.edit_pull_body(pull.number, land.with_images(pull.body, images))
    return render.added_report(pull.number, land.EVIDENCE_BRANCH, commit, [url for _, url in images])


def settled_pull(gh: GitHub, number: int) -> land.LandPull:
    """GitHub works out `mergeable` in the background after each push, so the first reads after a push can say UNKNOWN."""
    pull = gh.land_pull(number)
    for _ in range(MERGEABLE_READS - 1):
        if pull.state != "OPEN" or pull.mergeable != "UNKNOWN":
            break
        time.sleep(2)
        pull = gh.land_pull(number)
    return pull


def land_verb(gh: GitHub, args: argparse.Namespace) -> str:
    root = checkout_root(gh)
    here = str(root.resolve())
    pull = settled_pull(gh, args.number)
    if pull.state != "OPEN":
        raise CliError(render.land_refusal(pull.number, [f"the pull request is {pull.state.lower()}."]), REFUSED)
    workflow = gate_rules(gh, root, pull)
    commands = land.checks(workflow)
    found = land.evidence(workflow, pull.paths, pull.body)
    commit = gh.head_commit()
    reasons = land.refusals(
        pull, gh.current_branch(), commit, gh.tree_has_changes(), gh.commits_behind(pull.base), found, commands, sync_blockers(gh, pull, here, commit)
    )
    if reasons:
        raise CliError(render.land_refusal(pull.number, reasons), REFUSED)
    for command in commands:
        code = run.run_command(shlex.split(command), None, 15, gh, sys.stdout, cwd=root)
        if code != 0:
            raise CliError(render.land_refusal(pull.number, [f"the check `{command}` exited {code} on {pull.head}."]), REFUSED)
    if gh.tree_has_changes() or gh.head_commit() != pull.head_commit:
        raise CliError(render.land_refusal(pull.number, ["the checks changed tracked files or moved HEAD. Restore the checkout, then run the command again."]), REFUSED)
    confirm_merge(gh, pull)
    try:
        notes = sync(gh, pull, here)
    except CliError as error:
        raise CliError(f"PR #{pull.number} is merged, but the checkout is not synced: {error}") from None
    return render.land_report(pull.number, pull.url, pull.base, notes)


def confirm_merge(gh: GitHub, pull: land.LandPull) -> None:
    """Merges, then reads the state of the pull request, because the exit code of gh does not say whether it is merged.

    gh merges first and deletes the remote branch second, so it can fail after the merge is done. With a merge queue
    it can end without an error and without a merge.
    """
    failure = None
    try:
        gh.merge(pull.number, land.MERGE_METHOD, pull.head_commit)
    except CliError as error:
        failure = error
    try:
        state = gh.pull_state(pull.number)
    except CliError:
        raise (failure or CliError(f"gh pr merge ended without an error, but the state of PR #{pull.number} cannot be read. The checkout is not synced.")) from None
    if state != "MERGED":
        raise failure or CliError(f"gh pr merge ended without an error, but PR #{pull.number} is {state.lower()}, not merged. The checkout is as it was.")
    if failure:
        print(f"Note: gh reported a problem after the merge: {failure}", file=sys.stderr)


def sync_blockers(gh: GitHub, pull: land.LandPull, here: str, commit: str) -> list[str]:
    """The reasons, known before the merge, why `sync` would fail after it. A failure after the merge leaves a merged pull request and a checkout that is not synced.

    `commit` is HEAD of the checkout. It is the commit that the merge brings in, because the gate refuses every other HEAD.
    """
    trees = gh.worktrees()
    main, branch = trees[0]
    in_main = str(Path(main).resolve()) == here
    reasons = []
    holder = next((path for path, held in trees[1:] if held == pull.base), None)
    if in_main and holder:
        reasons.append(f"the base branch {pull.base} is checked out in the worktree {holder}, so this checkout cannot switch to it after the merge.")
    moved = here if in_main else main if branch == pull.base else None
    ahead = gh.commits_ahead(moved, pull.base, commit) if moved else 0
    if ahead:
        reasons.append(f"the local branch {pull.base} has {render.plural(ahead, 'commit')} that the merge will not hold, so it cannot be fast-forwarded after the merge.")
    return reasons


def sync(gh: GitHub, pull: land.LandPull, here: str) -> list[str]:
    """After the merge: moves a checkout to the merged base branch and drops the PR branch. Returns one line per thing done.

    The main checkout switches to the base branch and is fast-forwarded. From a linked worktree, the main checkout is
    fast-forwarded when it is on the base branch and left alone when it is not, and the worktree is removed. A worktree
    with a changed or an untracked file stays, and so does one whose submodule holds a commit that no remote has, and a
    branch or a worktree that moved after the merge.
    """
    main, branch = gh.worktrees()[0]
    gh.fetch(main)
    if str(Path(main).resolve()) == here:
        gh.switch(pull.base)
        gh.fast_forward(here, pull.base)
        return [f"This checkout is on {pull.base} at {gh.short_head(here)}.", drop_branch(gh, here, pull)]
    if branch == pull.base:
        gh.fast_forward(main, pull.base)
        notes = [f"The main checkout {main} is on {pull.base} at {gh.short_head(main)}."]
    else:
        notes = [f"The main checkout {main} is on {branch or 'a detached HEAD'}, so it was not moved. origin/{pull.base} has the merge."]
    status = gh.status(here)
    unsaved = [line[3:] for line in status if not line.startswith("!!")]
    stranded = [] if unsaved else gh.unpushed_in_submodules(here)
    if unsaved or stranded or gh.head_commit() != pull.head_commit:
        if unsaved:
            why = f"it has changed or untracked files ({render.some(unsaved, 1)})"
        elif stranded:
            why = f"a submodule in it holds a commit, a branch or a stash that no remote has ({stranded[0][:8]})"
        else:
            why = "its HEAD moved after the merge"
        return [*notes, f"Kept the worktree {here} and the branch {pull.head}: {why}. To remove it, run `git -C {main} worktree remove --force {here}`."]
    ignored = [line[3:] for line in status if line.startswith("!!")]
    gh.remove_worktree(main, here)
    notes.append(f"Removed the worktree {here}. Run `cd {main}`.")
    if ignored:
        notes.append(f"Git-ignored paths that went with it: {render.some(ignored, 5)}.")
    return [*notes, drop_branch(gh, main, pull)]


def drop_branch(gh: GitHub, checkout: str, pull: land.LandPull) -> str:
    if gh.branch_commit(checkout, pull.head) != pull.head_commit:
        return f"Kept the local branch {pull.head}: it moved after the merge."
    gh.delete_branch(checkout, pull.head)
    return f"Deleted the local branch {pull.head}."


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

    brief_parser = verbs.add_parser("brief", help="the parts of docs/agents/workflow.md that a stage needs, then the issue or PR")
    brief_parser.add_argument("stage", type=stage_arg, metavar="STAGE", help=f"one of {', '.join(brief.STAGES)}, or {', '.join(brief.COMMAND_NAMES)}")
    brief_parser.add_argument("number", type=issue_number, nargs="?", metavar="N", help="the PR for review, else the issue; leave out to print the rules only")
    brief_parser.add_argument("--full", action="store_true", help="passed to issue or pr")
    brief_parser.set_defaults(handler=brief_verb)

    next_verb_parser = verbs.add_parser("next", help="what to do next: PRs to review, tasks to build, issues to plan, spec or refine")
    next_verb_parser.set_defaults(handler=next_verb)

    next_cmd = verbs.add_parser("next-cmd", help="the one paste line that ends a stage")
    next_cmd.add_argument("stage", choices=("review", "build", "plan", "spec"))
    next_cmd.add_argument("number", type=issue_number, metavar="N", help="the PR for review, the parent for build, the issue for plan and spec")
    next_cmd.add_argument("--whole", action="store_true", help="for build: print the parent, which builds every open sub-issue on one branch, and not the next task")
    next_cmd.set_defaults(handler=next_cmd_verb)

    claim = verbs.add_parser("claim", help="assign an issue to @me and make its branch from the default branch")
    claim.add_argument("number", type=issue_number, metavar="N")
    claim.add_argument("--type", type=branch_kind, metavar="TYPE", help="branch type (default: fix for a bug label, else feat)")
    claim.add_argument("--no-branch", action="store_true", help="assign only, make no branch")
    claim.add_argument("--no-assign", action="store_true", help="make the branch only, assign no one")
    claim.add_argument("--auto", action="store_true", help="for /build auto: assign only, and count an open blocker as done when a commit on this branch ends its subject with (#N)")
    claim.set_defaults(handler=claim_verb)

    frontier = verbs.add_parser("frontier", help="the open sub-issues of P and the next one to build")
    frontier.add_argument("number", type=issue_number, metavar="P")
    frontier.set_defaults(handler=frontier_verb)

    ac = verbs.add_parser("ac", help="list the acceptance criteria boxes of an issue, or tick some of them")
    ac.add_argument("number", type=issue_number, metavar="N")
    ac.add_argument("--tick", type=box_list, metavar="LIST", help="the box numbers to tick, such as 1,3; every other line of the body stays the same")
    ac.set_defaults(handler=ac_verb)

    decide = verbs.add_parser("decide", help="post the decisions on stdin as one decision comment on an issue, and print its URL")
    decide.add_argument("number", type=issue_number, metavar="N")
    decide.add_argument("--from", dest="stage", type=stage_arg, required=True, metavar="STAGE", help=f"one of {', '.join(brief.STAGES)}, or {', '.join(brief.COMMAND_NAMES)}")
    decide.add_argument("--pr", type=issue_number, metavar="P", help="the pull request the decisions came from")
    decide.set_defaults(handler=decide_verb)

    evidence = verbs.add_parser(
        "evidence",
        help="check that a pull request that changes an evidence path shows an image in its Verification section, or add images to it",
        description="Exits 1 when the pull request changes a path under the `## Evidence paths` heading of docs/agents/workflow.md and its body has no "
        "`## Verification` section with an image. With --add, pushes the images to the evidence branch of the repo and writes them into that section.",
    )
    evidence.add_argument("number", type=issue_number, metavar="PR")
    evidence.add_argument("--add", nargs="+", type=Path, metavar="IMAGE", help="image files to push to the evidence branch and show in the Verification section")
    evidence.set_defaults(handler=evidence_verb)

    land_parser = verbs.add_parser(
        "land",
        help="run the checks of the repo on the PR branch, merge the pull request and sync the checkout",
        description="Run it on the PR branch. Exits 1 and merges nothing when the pull request is not open, is a draft, has merge conflicts, is behind its "
        "base branch, has no review decision comment or lacks evidence, when the checkout has changed tracked files or is not at the head commit of the "
        "pull request, or when docs/agents/workflow.md has no command under `## Checks` or one of them fails. Otherwise it merges, moves the checkout to "
        "the base branch, and deletes the PR branch and its worktree.",
    )
    land_parser.add_argument("number", type=issue_number, metavar="PR")
    land_parser.set_defaults(handler=land_verb)

    run_parser = run.add_parser(verbs)
    run_parser.set_defaults(handler=None, run_parser=run_parser)
    return parser


def main(argv: list[str] | None = None, runner: Runner = run_process) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as stop:
        return int(stop.code or 0)
    if args.verb == "run":
        try:
            return run.run_verb(GitHub(runner, args.repo), args, args.run_parser)
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
