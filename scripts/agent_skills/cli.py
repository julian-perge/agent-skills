import argparse
import os
import re
import shlex
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path

from agent_skills import REFUSED, CliError, brief, land, render, run, tracker
from agent_skills.github import GitHub, Runner, run_process

Handler = Callable[[GitHub, argparse.Namespace], str]
GATE_FILE = "docs/agents/workflow.md"
REVIEWS_DIR = "docs/reviews"
# These repos may have a GitHub origin and must still never push, so land --local accepts them.
LOCAL_ONLY_REPOS = frozenset({"osrs-shorts", "osrs-handoff"})
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


def one_line(value: str) -> str:
    if not value.strip() or "\n" in value:
        raise argparse.ArgumentTypeError("expected one line of text")
    return value.strip()


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
    if args.whole and args.stage != "build":
        raise CliError("--whole goes with the build stage only.")
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
    if args.local:
        return decide_local(gh, args)
    if args.number is None:
        raise CliError("decide needs the issue number N, or --local for the review of a branch in a repo with no GitHub remote.")
    if args.stage == "review" and args.reviewer is None:
        raise CliError(
            'Nothing posted: a review decision needs --reviewer <text> that names the agent that reviewed the PR, such as "agent-skills:code-reviewer subagent". '
            "`agent-skills land` refuses a review decision without it.",
            REFUSED,
        )
    if args.stage == "review" and args.pr is None:
        raise CliError("Nothing posted: a review decision needs --pr <n>, because `agent-skills land` reads the head commit that it records.", REFUSED)
    if args.stage != "review" and args.reviewer is not None:
        raise CliError("--reviewer goes with --from review only.")
    body = sys.stdin.read().strip()
    if not body:
        raise CliError("Nothing posted: the decisions come on stdin, and stdin was empty.", REFUSED)
    target = f"PR #{args.pr}" if args.pr is not None else f"#{args.number}"
    header = f"### Decisions from the {args.stage} of {target}"
    first, _, rest = body.partition("\n")
    if first.strip() == header:
        body = rest.strip()
    if args.stage == "review":
        body = f"Reviewed head: {gh.pull_head(args.pr)}\nReviewer: {args.reviewer}\n\n{body}"
    return gh.comment(args.number, f"{header}\n\n{body}").strip() + "\n"


def decide_local(gh: GitHub, args: argparse.Namespace) -> str:
    """Writes the review of the current branch to its review file and commits only that file. It never pushes."""
    if args.stage != "review":
        raise CliError("--local goes with --from review only.")
    if args.number is not None or args.pr is not None:
        raise CliError("--local takes no issue number and no --pr: the review goes to a file on the branch.")
    if args.reviewer is None:
        raise CliError(
            'Nothing written: a local review needs --reviewer <text> that names the agent that reviewed the branch, such as "agent-skills:code-reviewer subagent". '
            "`agent-skills land --local` refuses a review without it.",
            REFUSED,
        )
    body = sys.stdin.read().strip()
    if not body:
        raise CliError("Nothing written: the decisions come on stdin, and stdin was empty.", REFUSED)
    root = checkout_root(gh)
    branch = gh.current_branch()
    base = default_local_branch(gh, root)
    if branch == "HEAD":
        raise CliError("Nothing written: HEAD is detached. Switch to the branch that was reviewed.", REFUSED)
    if branch == base:
        raise CliError(f"Nothing written: this checkout is on the base branch {base}. Switch to the branch that was reviewed.", REFUSED)
    if gh.tree_has_changes():
        raise CliError("Nothing written: the working tree has changes. Commit or stash them, so that the review covers a commit.", REFUSED)
    header = f"### Decisions from the review of {branch}"
    first, _, rest = body.partition("\n")
    if first.strip() == header:
        body = rest.strip()
    path = review_path(branch)
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{header}\n\nReviewed head: {gh.head_commit()}\nReviewer: {args.reviewer}\n\n{body}\n")
    commit = gh.commit_path(str(root), path, f"docs: record the review of {branch}")
    return f"{path}\n{commit}\n"


def review_path(branch: str) -> str:
    return f"{REVIEWS_DIR}/{branch.replace('/', '-')}.md"


def default_local_branch(gh: GitHub, root: Path) -> str | None:
    """The base branch of a repo with no remote: main when it exists, else master, else None."""
    return next((name for name in ("main", "master") if gh.has_ref(str(root), f"refs/heads/{name}")), None)


def gate_rules(gh: GitHub, root: Path, pull: land.LandPull) -> str:
    """The text of docs/agents/workflow.md that judges a pull request.

    It comes from the base branch, so a pull request cannot weaken its own gate. When the base branch has no such
    file yet, it comes from the checkout. Each of the two cases that can surprise prints a note to stderr.
    """
    gh.fetch(str(root))
    if not gh.has_ref(str(root), f"origin/{pull.base}"):
        raise CliError(f"This clone has no origin/{pull.base}, so the gate of the base branch cannot be read. Run `git fetch origin {pull.base}:refs/remotes/origin/{pull.base}`, then run the command again.")
    return gate_text(gh, root, f"origin/{pull.base}", pull.base, GATE_FILE in pull.paths, "this pull request")


ANY_CHECKS_HEADING = re.compile(r"^[^\w#]{0,4}#+\s*checks\b", re.IGNORECASE | re.MULTILINE)


def gate_text(gh: GitHub, root: Path, ref: str, base: str, changed: bool, change: str) -> str:
    """The text of docs/agents/workflow.md at `ref`, or in the checkout when `ref` has none or has one with no checks. `changed` says whether `change` edits the file."""
    text = gh.file_at(ref, GATE_FILE)
    if text is None:
        text = workflow_text(root)
        print(f"Note: {base} has no {GATE_FILE} yet, so the gate comes from this checkout.", file=sys.stderr)
    elif not ANY_CHECKS_HEADING.search(text) and (root / GATE_FILE).is_file() and land.checks(mine := workflow_text(root)):
        # A base file with no Checks heading at any level can never pass, so the setup that adds the first checks to an older repo could never land. That file holds no gate to weaken. A base with a Checks heading that cannot be read still judges the pull request.
        text = mine
        print(f"Note: the {GATE_FILE} of {base} has no `## Checks` yet, so the gate comes from this checkout.", file=sys.stderr)
    elif changed:
        print(f"Note: {change} changes {GATE_FILE}. The gate comes from {base}.", file=sys.stderr)
    problems = land.workflow_problems(text)
    if problems:
        raise CliError("\n".join([f"{GATE_FILE} has list items that cannot be read:", *(f"- {problem}" for problem in problems)]))
    return text


def stale_review(gh: GitHub, root: Path, pull: land.LandPull) -> list[str]:
    """Why the newest review decision does not cover the change at the head of the pull request. Fetch origin first.

    A review of an older commit still counts when the change of the pull request has the same patch-id at both commits,
    as after a rebase or a merge of the base branch. A note on stderr then says so.
    """
    decision = land.review_decision(pull.number, pull.comments)
    reviewed = land.review_line(decision, land.REVIEWED_HEAD) if decision else None
    if reviewed is None or reviewed.lower() == pull.head_commit.lower():
        return []
    again = "Review the PR again and post the decision with `agent-skills decide`."
    for commit in (reviewed, pull.head_commit):
        if not gh.get_commit(str(root), commit):
            return [f"the review covers {reviewed[:8]}, but this clone does not have commit {commit[:8]} and `git fetch origin {commit}` cannot get it, so the two changes cannot be compared. {again}"]
    before, after = (gh.patch_id(str(root), f"origin/{pull.base}", commit) for commit in (reviewed, pull.head_commit))
    if before != after:
        return [f"the review covers {reviewed[:8]}, but the PR head is {pull.head_commit[:8]} and its change differs. {again}"]
    print(f"Note: the review covers {reviewed[:8]} and the PR head is {pull.head_commit[:8]}, but the change of the pull request has the same patch-id at both, so the review still counts.", file=sys.stderr)
    return []


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
    if args.local:
        if args.number is not None:
            raise CliError("land --local takes no PR number: it lands the current branch.")
        return land_local_verb(gh, args)
    if args.number is None:
        raise CliError("land needs the PR number, or --local to land the current branch in a repo with no GitHub remote.")
    if args.base is not None:
        raise CliError("--base goes with --local only.")
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
        pull, gh.current_branch(), commit, gh.tree_has_changes(), gh.commits_behind(pull.base), found, commands, sync_blockers(gh, pull, here, commit), stale_review(gh, root, pull)
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


def land_local_verb(gh: GitHub, args: argparse.Namespace) -> str:
    """Lands the current branch into a local base branch with a merge commit. It never fetches or pushes."""
    root = checkout_root(gh)
    here = str(root.resolve())
    trees = gh.worktrees()
    main = trees[0][0]
    url = gh.origin_url()
    if url and "github.com" in url.lower() and Path(main).name not in LOCAL_ONLY_REPOS:
        raise CliError(f"Not landed: origin points at GitHub ({url}). Push the branch, open a pull request and run `agent-skills land <pr>`.", REFUSED)
    base = args.base or default_local_branch(gh, root)
    if base is None:
        raise CliError("This repo has no main or master branch. Pass --base <branch>.")
    if not gh.has_ref(here, f"refs/heads/{base}"):
        raise CliError(f"This repo has no local branch {base}.")
    branch = gh.current_branch()
    if branch in ("HEAD", base):
        where = "HEAD is detached" if branch == "HEAD" else f"this checkout is on the base branch {base}"
        raise CliError(render.branch_refusal(branch, [f"{where}. Switch to the branch to land."]), REFUSED)
    workflow = gate_text(gh, root, base, base, GATE_FILE in gh.changed_paths(f"{base}...HEAD"), "this branch")
    commands = land.checks(workflow)
    commit = gh.head_commit()
    reasons = []
    if gh.tree_has_changes():
        reasons.append("the working tree has changes. Commit them, or stash them.")
    behind = gh.commits_missing(base)
    if behind:
        reasons.append(
            f"the branch is {render.plural(behind, 'commit')} behind {base}, so the checks would not test the merged code. "
            f"Run `git merge {base}` or `git rebase {base}` on the branch, and run the command again."
        )
    target, blocked = local_merge_target(gh, trees, here, base)
    reasons += local_review_problems(gh, here, branch, base, commit)
    if not commands:
        reasons.append(f"{GATE_FILE} has no `## Checks` heading with a command, so the checks of the repo cannot run.")
    reasons += blocked
    if reasons:
        raise CliError(render.branch_refusal(branch, reasons), REFUSED)
    for command in commands:
        code = run.run_command(shlex.split(command), None, 15, gh, sys.stdout, cwd=root)
        if code != 0:
            raise CliError(render.branch_refusal(branch, [f"the check `{command}` exited {code} on {branch}."]), REFUSED)
    if gh.tree_has_changes() or gh.head_commit() != commit:
        raise CliError(render.branch_refusal(branch, ["the checks changed tracked files or moved HEAD. Restore the checkout, then run the command again."]), REFUSED)
    if target == here:
        gh.switch(base)
    merged = gh.merge_no_ff(target, branch)
    if merged.returncode != 0:
        gh.abort_merge(target)
        if target == here:
            gh.switch(branch)
        raise CliError(render.branch_refusal(branch, [merge_failure(merged.stdout + merged.stderr, target, branch, base)]), REFUSED)
    landed = gh.short_head(target)
    try:
        notes = local_sync(gh, main, here, target, branch, base, commit)
    except CliError as error:
        raise CliError(f"{branch} is merged into {base}, but the checkout is not synced: {error}") from None
    return "\n".join([f"Landed {branch} into {base} at {landed}.", *notes]) + "\n"


def merge_failure(output: str, checkout: str, branch: str, base: str) -> str:
    """Why `git merge` failed, from its output: untracked files in the way, or else a conflict."""
    lines = output.strip().splitlines()
    aborted = f"The merge is aborted and {base} is as it was."
    if any("untracked working tree files would be overwritten" in line for line in lines):
        start = next(index for index, line in enumerate(lines) if "untracked working tree files would be overwritten" in line)
        names = [line.strip() for line in lines[start + 1 :] if line.startswith("\t")]
        listed = f" ({render.some(names, 5)})" if names else ""
        return f"untracked files in {checkout}{listed} block the merge of {branch} into {base}. {aborted} Move or remove them, and run the command again."
    why = next((line for line in lines if "CONFLICT" in line), lines[-1] if lines else "no output")
    return f"`git merge --no-ff {branch}` into {base} failed ({why}). {aborted} Run `git merge {base}` on the branch, fix the conflicts, and run the command again."


def local_merge_target(gh: GitHub, trees: list[tuple[str, str | None]], here: str, base: str) -> tuple[str, list[str]]:
    """The checkout where the merge runs, and the reasons why it cannot run there.

    The merge runs in this checkout after a switch to the base branch. When this checkout is a linked worktree and the main
    checkout is on the base branch, the merge runs in the main checkout, as the GitHub land fast-forwards it.
    """
    main = str(Path(trees[0][0]).resolve())
    holder = next((str(Path(path).resolve()) for path, held in trees if held == base), None)
    if holder is None:
        return here, []
    if holder == main and here != main:
        if gh.tree_has_changes(main):
            return main, [f"the main checkout {main} is on {base} and has changed tracked files, so the merge cannot run there. Commit them, or stash them."]
        return main, []
    return here, [f"the base branch {base} is checked out in the worktree {holder}, so this checkout cannot switch to it for the merge."]


def local_review_problems(gh: GitHub, here: str, branch: str, base: str, head: str) -> list[str]:
    """Why the review file of the branch does not cover the change at HEAD. A note on stderr says when a review of an older commit still counts."""
    path = review_path(branch)
    decide = "`agent-skills decide --from review --local --reviewer <text>`"
    record = gh.file_at("HEAD", path)
    if record is None:
        return [f"this branch has no review file {path}. A reviewer that did not write the code records it with {decide}."]
    missing = [f"no `{label}` line" for label, pattern in (("Reviewed head:", land.REVIEWED_HEAD), ("Reviewer:", land.REVIEWER)) if land.review_line(record, pattern) is None]
    if missing:
        return [f"{path} has {' and '.join(missing)}. The reviewer records the review again with {decide}, which writes both lines."]
    reviewed = land.review_line(record, land.REVIEWED_HEAD) or ""
    again = f"Review the branch again and record the review with {decide}."
    if not gh.has_ref(here, reviewed):
        return [f"the review covers {reviewed[:8]}, but this repo does not have that commit, so the two changes cannot be compared. {again}"]
    if reviewed.lower() == head.lower():
        return []
    # Only the patch-id accepts an older review. A tree that differs only by the review file does not, because a merge of the base branch with -s ours keeps that tree and drops the change of the base branch.
    paths = (".", f":(exclude){REVIEWS_DIR}")
    before, after = (gh.patch_id(here, base, commit, paths) for commit in (reviewed, head))
    if before != after:
        return [f"the review covers {reviewed[:8]}, but HEAD is {head[:8]} and the change of the branch differs. {again}"]
    if gh.changed_paths(reviewed, head) != [path]:
        print(f"Note: the review covers {reviewed[:8]} and HEAD is {head[:8]}, but the change of the branch has the same patch-id at both, so the review still counts.", file=sys.stderr)
    return []


def local_sync(gh: GitHub, main: str, here: str, target: str, branch: str, base: str, commit: str) -> list[str]:
    """After the merge: deletes the branch and removes its linked worktree, unless the worktree holds unsaved work. Returns one line per thing done."""
    if here == str(Path(main).resolve()):
        gh.delete_merged_branch(here, branch, base)
        return [f"This checkout is on {base}.", f"Deleted the local branch {branch}."]
    notes = [f"The main checkout {main} is on {base}." if target != here else f"The worktree {here} is on {base}."]
    status = gh.status(here)
    unsaved = [line[3:] for line in status if not line.startswith("!!")]
    stranded = [] if unsaved else gh.unpushed_in_submodules(here)
    moved = target != here and gh.head_commit() != commit
    if unsaved or stranded or moved:
        if unsaved:
            why = f"it has changed or untracked files ({render.some(unsaved, 1)})"
        elif stranded:
            why = f"a submodule in it holds a commit, a branch or a stash that no remote has ({stranded[0][:8]})"
        else:
            why = "its HEAD moved after the merge"
        if target != here:
            return [*notes, f"Kept the worktree {here} and the branch {branch}: {why}. To remove it, run `git -C {main} worktree remove --force {here}`."]
        gh.delete_merged_branch(here, branch, base)
        return [*notes, f"Deleted the local branch {branch}.", f"Kept the worktree {here}: {why}. To remove it, run `git -C {main} worktree remove --force {here}`."]
    ignored = [line[3:] for line in status if line.startswith("!!")]
    gh.remove_worktree(main, here)
    notes.append(f"Removed the worktree {here}. Run `cd {main}`.")
    if ignored:
        notes.append(f"Git-ignored paths that went with it: {render.some(ignored, 5)}.")
    gh.delete_merged_branch(main, branch, base)
    notes.append(f"Deleted the local branch {branch}.")
    return notes


CLAUDE_FILES = ("CLAUDE.md", ".claude/CLAUDE.md")
FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+).+?\1")


def import_targets(claude_text: str) -> Iterator[str]:
    """Yield the path of each @ token that Claude Code reads as an import.

    Claude Code skips imports in code blocks and code spans, and it hides HTML comments, so doctor skips @ tokens in all three.
    """
    fence = ""
    in_comment = False
    for line in claude_text.splitlines():
        if fence:
            closing = line.strip()
            if closing.startswith(fence) and set(closing) == {fence[0]}:
                fence = ""
            continue
        if not in_comment and (opened := FENCE.match(line)):
            fence = opened.group(1)
            continue
        kept = ""
        while line:
            if in_comment:
                end = line.find("-->")
                if end < 0:
                    break
                line, in_comment = line[end + 3 :], False
            else:
                start = line.find("<!--")
                if start < 0:
                    kept += line
                    break
                kept += line[:start] + " "
                line, in_comment = line[start + 4 :], True
        for token in CODE_SPAN.sub(" ", kept).split():
            if token.startswith("@"):
                yield token[1:]


def imports_agents_file(claude: Path, agents: Path) -> bool:
    try:
        text = claude.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CliError(f"{claude} is not UTF-8 text (byte {error.start} is not valid), so doctor cannot read its imports. Save it as UTF-8.") from error
    return any(
        not target.startswith(("/", "~")) and Path(os.path.normpath(claude.parent / target)) == agents for target in import_targets(text)
    )


def doctor_verb(gh: GitHub, args: argparse.Namespace) -> str:
    root = checkout_root(gh)
    agents = root / "AGENTS.md"
    if not agents.is_file():
        return "No AGENTS.md in this repo, so CLAUDE.md needs no import.\n"
    claudes = [root / name for name in CLAUDE_FILES if (root / name).is_file()]
    if not claudes:
        if (root / "CLAUDE.local.md").is_file():
            raise CliError(
                "CLAUDE.local.md exists and CLAUDE.md does not. When a CLAUDE file exists, Claude Code reads it instead of AGENTS.md, "
                "so it never loads the rules in AGENTS.md. Create CLAUDE.md with the line `@AGENTS.md`.",
                REFUSED,
            )
        # Claude Code also reads CLAUDE files in every parent folder, and one there stops the AGENTS.md fallback. The one in ~/.claude is user memory and does not.
        for folder in root.parents:
            for name in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"):
                found = folder / name
                if found.is_file() and found != Path.home() / ".claude/CLAUDE.md":
                    raise CliError(
                        f"{found} exists in a parent folder, so Claude Code reads it and not AGENTS.md. "
                        "Create CLAUDE.md in this repo with the line `@AGENTS.md`.",
                        REFUSED,
                    )
        return "No CLAUDE.md in this repo or its parent folders, so Claude Code reads AGENTS.md itself.\n"
    for claude in claudes:
        name = claude.relative_to(root).as_posix()
        if claude.is_symlink() and claude.resolve() == agents.resolve():
            return f"{name} is a link to AGENTS.md, so Claude Code reads AGENTS.md.\n"
        if imports_agents_file(claude, agents):
            return f"{name} imports AGENTS.md.\n"
    names = [claude.relative_to(root).as_posix() for claude in claudes]
    fix = "@AGENTS.md" if names[0] == "CLAUDE.md" else "@../AGENTS.md"
    raise CliError(
        f"{' and '.join(names)} {'do' if len(names) > 1 else 'does'} not import AGENTS.md. When {names[0]} exists, Claude Code reads it "
        f"instead of AGENTS.md, so it never loads the rules in AGENTS.md. Add the line `{fix}` to {names[0]}, outside any code block or HTML comment.",
        REFUSED,
    )


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

    decide = verbs.add_parser(
        "decide",
        help="post the decisions on stdin as one decision comment on an issue, and print its URL. With --local, commit a review to a file on the branch",
        description="Posts the decisions on stdin as one comment on issue N and prints its URL. With --from review --local --reviewer <text>, it takes no N: "
        f"it writes {REVIEWS_DIR}/<branch, with / as ->.md on the current branch with the reviewed head and the reviewer, commits only that file, "
        "and prints the path and the commit. It never pushes. It exits 1 and writes nothing on the base branch, on a working tree with changes, "
        "without --reviewer or with empty stdin.",
    )
    decide.add_argument("number", type=issue_number, nargs="?", metavar="N", help="the issue that gets the comment. Leave it out with --local")
    decide.add_argument("--from", dest="stage", type=stage_arg, required=True, metavar="STAGE", help=f"one of {', '.join(brief.STAGES)}, or {', '.join(brief.COMMAND_NAMES)}")
    decide.add_argument("--pr", type=issue_number, metavar="P", help="the pull request the decisions came from. Needed with --from review, where the comment also records its head commit")
    decide.add_argument("--reviewer", type=one_line, metavar="TEXT", help="needed with --from review: the agent that reviewed the PR, such as \"agent-skills:code-reviewer subagent\". It is recorded, not verified")
    decide.add_argument("--local", action="store_true", help=f"with --from review: record the review of the current branch in {REVIEWS_DIR}/ for `land --local`, in a repo with no GitHub remote")
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
        "base branch, has no review decision comment that covers the change at its head or lacks evidence, when the checkout has changed tracked files or is not at the head commit of the "
        "pull request, or when docs/agents/workflow.md has no command under `## Checks` or one of them fails. Otherwise it merges, moves the checkout to "
        "the base branch, and deletes the PR branch and its worktree. "
        "With --local, in a repo with no GitHub remote: it lands the current branch into its local base branch with `git merge --no-ff`. "
        "It reads the gate from the base branch, and needs a review file from `decide --from review --local` that covers the change at HEAD. "
        "It exits 1 and merges nothing on the base branch, on a working tree with changes, on a branch behind the base branch, when the base branch is "
        "checked out in another worktree, when the review file is missing, lacks a line or is stale, when a check fails, on a merge conflict, and "
        "when origin points at GitHub. Then it deletes the branch and its worktree. It never fetches or pushes.",
    )
    land_parser.add_argument("number", type=issue_number, nargs="?", metavar="PR", help="the pull request. Leave it out with --local")
    land_parser.add_argument("--local", action="store_true", help="land the current branch into its local base branch, in a repo with no GitHub remote")
    land_parser.add_argument("--base", metavar="BRANCH", help="with --local: the branch to land into (default: main, else master)")
    land_parser.set_defaults(handler=land_verb)

    doctor = verbs.add_parser(
        "doctor",
        help="check that Claude Code loads AGENTS.md: when CLAUDE.md or .claude/CLAUDE.md exists, it must import AGENTS.md",
        description="Reads only the files of the checkout and calls no gh command. Exits 1 when AGENTS.md exists, a CLAUDE.md or .claude/CLAUDE.md exists, "
        "and none of them imports AGENTS.md or is a link to it. Exits 2 when a CLAUDE.md is not UTF-8.",
    )
    doctor.set_defaults(handler=doctor_verb)

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
