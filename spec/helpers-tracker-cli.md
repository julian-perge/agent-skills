# Spec: tracker-cli, V1

Module of [helpers-map.md](helpers-map.md). It inherits the tech stack, commands, code style and boundaries there.

## Objective

In 47 stage sessions (urchin, blender-addon-rs317-667mqo-makeup), the first 3 to 6 Bash calls rebuilt the same `gh` queries. The agents read the issue twice, because `gh issue view N --comments` prints only the comments when stdout is not a terminal. They read `docs/agents/issue-tracker.md` for the syntax, then queried blockers and sub-issues one by one. `gh issue view` appeared in about 15 forms (1,010 uses, 231 sessions).

`agent-skills <verb>` replaces each of those lookups with one call that has a fixed output. The users are the agents that run `/agent-skills` stages in Claude Code, Codex and the OpenCode workers. The user also runs `next` directly.

## Interface

```
agent-skills [--repo OWNER/REPO] <verb> [args]
```

- **Repo:** by default, parsed from `git remote get-url origin` (HTTPS or SSH form). Every `gh` call gets `--repo`, or a `repos/<owner>/<repo>` path, so a fork with an `upstream` remote never targets the parent.
- **Output:** Markdown on stdout. Errors go to stderr.
- **Exit codes:** 0 done. 1 refused: a precondition failed, and the reason is printed. 2 usage or environment error: no `gh`, not signed in, no `origin`, or an API error.

### `issue N [--full]`

A single GraphQL query reads: number, title, state, url, body, labels, assignees, `parent { number title body }`, `subIssuesSummary { total completed }` for the counts, `subIssues(first: 100)` (GitHub's cap per parent) with the state, assignee count and blocker count of each, `blockedBy(first: 20)`, `closedByPullRequestsReferences(first: 5, includeClosedPrs: true)`, and `comments(last: 20)` with `totalCount`. Each of these fields was checked against julian-perge/urchin#161 on 2026-11-15.

```
# #49 Region scenery [OPEN]
- Labels: ready-for-agent
- Assignee: none
- Parent: #35 Draynor region import
- Spec: spec/35-draynor-region-import.md (from parent body)
- Open blockers: none (closed: #47)
- Pull requests: #60 OPEN
- Sub-issues: 2 open of 5

| # | State | Assignee | Open blockers | Title |
...
## Body
...
## Comments (3 of 3, newest last)
### @julian-perge, 2026-11-12
...
```

- **Spec lookup:** the three rules of `next`. Rule 1: a `Spec` line or a `spec/...md` path in the issue body. Rule 2: the same in the parent body. Rule 3: exactly one file `spec/<issue>-*.md` or `spec/<parent>-*.md`, marked `(guess)`. When rule 3 finds several files, the line lists the candidates and names no spec.
- **Limits without `--full`:** the body is cut at 2,000 characters. Only the newest 3 comments show, each cut at 600 characters. The sub-issue table has at most 10 rows, open sub-issues first. Each cut ends with `[cut: <n> more characters, run with --full]`, and the table's cut says `<n> more rows`.

### `pr N [--full]`

A single GraphQL query reads: title, state, `isDraft`, url, body, `baseRefName`, `headRefName`, `closingIssuesReferences(first: 5)`, `files(first: 100)` with additions and deletions, `commits(last: 20)` headlines, the check rollup state of the last commit, and `reviews(last: 5)`.

- **Task:** taken from `closingIssuesReferences`. When that is empty, a `Closes #<n>` in the body. When that is missing too, the number in the branch name (`<type>/<n>-<slug>`), marked `(guess)`. Otherwise none.
- **Spec:** the spec lookup above, run on the task.
- **Standard:** `CODING_STANDARDS.md` when it exists at the repo root, else `AGENTS.md`, else `CLAUDE.md`.
- **Output:** a header, base and head, the draft flag, the checks state, the task with its title, spec and standard, a files table, the commit headlines and the body (cut as in `issue`). Then two lines:

```
Check out: gh pr checkout 60
Review: /agent-skills:review issue #43, PR #60, spec spec/35-draynor-region-import.md, standard CODING_STANDARDS.md
```

The review line leaves out each part that has no value.

### `claim N [--type TYPE] [--no-branch] [--no-assign] [--auto]`

1. **Refuse (exit 1, nothing changed)** when the issue is closed, has an assignee other than `@me`, or has an open blocker. Unless `--no-branch` is given, also refuse when the working tree has changes or the branch already exists.
2. **Assign:** `gh issue edit N --repo R --add-assignee @me`. Skip this step with `--no-assign`, or when `@me` is already the assignee.
3. **Branch:** `git fetch origin <default>`, then `git switch -c <type>/<N>-<slug> origin/<default>`. Skip this step with `--no-branch`. `<default>` comes from `git symbolic-ref refs/remotes/origin/HEAD`.
4. **Type and slug:** `TYPE` is `--type`, else `fix` when the labels include `bug`, else `feat`. The slug is the title in lowercase, letters and digits only, words joined with `-`, at most 5 words and 40 characters.
5. **Report:** one line, for example `Claimed #49 for @me. Branch feat/49-region-scenery from origin/main at 1a2b3c4.`

For `/agent-skills:build auto`: `claim <source> --no-assign` makes the one branch, and `claim <task> --auto` claims each task. `--auto` makes no branch, and it counts an open blocker as done when a subject of `git log --format=%s origin/<default>..HEAD` ends with `(#<blocker>)`, because every task stays open until the one pull request merges.

### `frontier P`

A table of the open sub-issues of `P` with assignee and open blockers. The last line is `Frontier: #<n>`, the lowest open number with the `ready-for-agent` label, no open blocker and no assignee. When there is no such issue, the last line is `Frontier: none (<reason>)`. Exit 0 in both cases.

### `next`

A port of the rules in today's `agent-skills-next` SKILL.md, unchanged:

- Preflight: stop when there is no `docs/agents/workflow.md` or the repo is in files mode.
- The groups Review, Build, Plan, Spec and Idea, in that priority.
- The frontier mark, at most five rows per group, and the Next block.
- The list of guesses.

Preflight stops exit 2 with the same messages as the skill. The same tracker state gives the same output, byte for byte.

### `next-cmd <stage> N`

Prints one paste line with no Markdown, for the end of a stage:

| Call | Prints | Exit 1 when |
| --- | --- | --- |
| `next-cmd review <pr>` | the review line of `pr` | never. The parts with no value are left out, and stderr names them |
| `next-cmd build <parent>` | `/agent-skills:build #<frontier>`, with the frontier rule of `frontier` | there is no frontier: no open sub-issue has `ready-for-agent`, no open blocker and no assignee |
| `next-cmd build <parent> --whole` | `/agent-skills:build #<parent>`, which builds every open sub-issue on one branch | there is no frontier, as above |
| `next-cmd plan <issue>` | `/agent-skills:plan #<issue>, spec <spec>` | the issue has no spec |
| `next-cmd spec <issue>` | `/agent-skills:spec #<issue>` | never |

## Project structure

```
bin/agent-skills                          launcher: resolves its real path, adds ../scripts to sys.path, calls agent_skills.cli.main()
scripts/agent_skills/__init__.py
scripts/agent_skills/cli.py               argparse, verb dispatch, exit codes
scripts/agent_skills/github.py            the only module that runs gh or git
scripts/agent_skills/tracker.py           pure rules: spec lookup, groups, frontier, PR task, slug, type
scripts/agent_skills/render.py            Markdown and one-line output
scripts/agent_skills/tests/test_*.py
scripts/agent_skills/tests/fixtures/      trimmed real gh responses and expected outputs
```

## Testing strategy

- **Framework:** `unittest`. `github.py` takes a runner object, and the tests pass a fake runner that maps an argv to a fixture and records every call.
- **Unit tests for `tracker.py`:** every rule, including the edge cases:
  - Each spec rule, several rule-3 candidates, and no spec.
  - Group priority, and a PR task from each source.
  - The frontier with blocked tasks and with assigned tasks.
  - Slug cutting, and the type from labels.
- **Golden tests for `render.py`:** `issue`, `pr`, `next` and `frontier` output from fixtures, compared byte for byte with expected files.
- **CLI tests:** the exit codes. The `--repo` value on every recorded call. For each refusal case, `claim` records no write call.
- **Fixtures:** trimmed from real responses of julian-perge/urchin and julian-perge/blender-addon-rs317-667mqo-makeup, fetched with the same query text the CLI sends.
- **CI:** one new step in `.github/workflows/test-plugin-install.yml` runs the unit-test command from the map.
- **Live check:** a manual smoke run of each read verb in urchin and blender. It is not run in CI.

## Success criteria

1. The unit tests pass locally and in CI.
2. `agent-skills next` run twice in blender, with no tracker change between the runs, prints the same output byte for byte, and its rows follow the rules of the old skill.
3. `agent-skills issue 107` in urchin prints at most 5,000 characters. It names the parent, the spec, the open blockers and the sub-issues. With `--full`, it prints the whole body and all comments.
4. For an open PR in blender, `agent-skills pr <n>` prints a review line that `/agent-skills:review` accepts with no edit.
5. `claim` on a closed issue, on an issue assigned to someone else and on a blocked issue exits 1, gives the reason, and records no write.
6. In `~/code/agent-skills`, which has an `upstream` remote, every recorded `gh` call names `julian-perge/agent-skills`.
7. `issue` makes one `gh` call. `pr` makes one, plus one when the task is not a closing reference. `frontier` makes one. `next` makes one call per page of issues, plus one call per Plan candidate.
8. `agent-skills --help` works through `~/.local/bin/agent-skills` and as a bare command in a Claude Code session (plugin `bin/`).

## Out of scope (deferred)

- **`--json` output:** the slice 2 brief-injection hook may need it.
- **Files mode in `next`:** no repo of the three runs the stages in files mode.
- **Verbs that create sub-issues or `blocked_by` edges:** the plan stage keeps the raw `gh` commands for these writes.
- **Caching responses between calls.**
- **A git orientation verb:** each `git status`/`log`/`diff` call is short already.

## Open questions

None.
