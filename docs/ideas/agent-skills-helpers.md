# agent-skills workflow helpers

## Problem Statement

How might we give every agent that runs an `/agent-skills` stage one fixed command per lookup, so that its first calls go to the task and not to rebuilding `gh` and `git` queries?

## Recommended Direction

Move `agent-skills-next` and `setup-agent-skills-workflow` from dotfiles into the fork `julian-perge/agent-skills`. On this Mac, `~/code/agent-skills` becomes the only copy that Claude Code, Codex, OpenCode and the shell run. Then add one Python CLI, `agent-skills`, with the verbs that agents now rebuild by hand. Edit the stage command files so that each stage starts with one call to a helper.

The evidence comes from 817 transcript files with 28,017 Bash calls, across urchin, blender-addon-rs317-667mqo-makeup and bustin-out-recomp (audit scripts: `~/tmp/2026-11-15-agent-cli-audit/`):

- **Stage openers:** each stage session starts with 3 to 6 calls. They read the issue twice, because `gh issue view N --comments` shows only the comments when stdout is not a TTY. They read `docs/agents/issue-tracker.md` for the syntax. Then they query the blockers and the sub-issues.
- **`gh issue view`:** about 15 different forms, 1,010 uses, 231 sessions.
- **Test runs piped to `tail`:** this is a larger cost. `uv run pytest | tail` has 1,091 uses, `test-blender.sh` 665 and `prek run | tail` 491. One build session ran `test-blender.sh -k pick` four times only to see a different tail length.

The fork diverges from upstream on purpose. Keep each edit to an upstream command file to one line, so that each upstream merge conflict is also one line.

## MVP Scope (slice 1)

- **Migration**
  - Copy the two skills and their 4 seed files into the fork. Delete them and their 3 symlinks from dotfiles.
  - In the fork's `.claude-plugin/marketplace.json`, set the plugin source to `./`. Today it points at `addyosmani/agent-skills`.
  - Claude Code (`dot_claude/settings.json.tmpl`): repoint the `addy-agent-skills` marketplace to the directory `~/code/agent-skills`.
  - Codex (`~/.codex/config.toml`, not in dotfiles today): repoint `[marketplaces.agent-skills]`, which still uses the upstream git URL. Codex already accepts a local path source (see `openai-bundled`).
  - OpenCode (`opencode.jsonc.tmpl`): point the skills path at `~/code/agent-skills/skills`.
  - Use chezmoi to link `~/.local/bin/agent-skills` to `~/code/agent-skills/bin/agent-skills`.
- **CLI** (`bin/agent-skills`): Python 3 stdlib only, with a PEP 723 header and `#!/usr/bin/env python3`. Every verb reads `--repo` from origin, so it is safe in a fork.
  - `next`: the agent-skills-next tables, with the rules ported 1:1. Tests run against recorded `gh` JSON fixtures.
  - `issue N`: a single brief with title, state, labels, assignee, parent, spec path, sub-issues, open blockers and comments. Long text is cut short. `--full` prints all of it.
  - `pr N`: the PR, its task (from `Closes #n` or the branch name), spec, standard, checks, `git diff base...head --stat`, and the exact review command.
  - `claim N`: assigns `@me`, fetches main, and runs `git switch -c <type>/<n>-<slug> origin/main`. It refuses when the issue already has an assignee or an open blocker.
  - `frontier P` and `next-cmd <stage>`.
  - `run -- <cmd>`: saves the full log and prints the exit code, the pass/fail lines without ANSI codes, the last 15 lines and the log path.
- **Fork edits:** `build.md`, `review.md`, `plan.md` and `spec.md` call the verbs. The seeded `workflow-github.md` and `issue-tracker-github.md` name the verbs instead of raw `gh` lines.
- **`enforce-tools.sh` rules** (Claude Code, Codex and OpenCode): block `gh issue view` with `--comments` and no `--json`, and block `gh` writes without `--repo` in a repo that has an `upstream` remote. Both messages name the helper to use.

Slice 2, after a measurement:

- A `## Commands` table that the setup skill seeds, plus `agent-skills verify` and `agent-skills test [filter]`.
- Summary output from the per-repo scripts. urchin already has `uv run gut`, and agents still pipe it through `sed`/`rg`. Add a `--summary` mode to blender's `test-blender.sh`, and a `check-all` command for bustin's `bodecomp`.
- A `UserPromptSubmit` hook that injects `issue N` for each issue number in the stage arguments.
- `agent-skills audit`.

## Key Assumptions to Validate

- [x] **Agents call the verbs when the command file names them.** Test: after slice 1, run 3 build and 2 review sessions in blender, then run `audit.py`. Targets: 1 Bash call before the first source read, and 0 raw `gh issue view` calls. Result: the agents call the verbs, but 2 of the 3 targets miss. See "Trial results" below.
- [ ] **Claude Code installs from a directory marketplace whose plugin source is `./`.** Test: check that `/agent-skills:build` resolves to `~/code/agent-skills` and not to the plugin cache.
- [ ] **The OpenCode workers and Codex see `~/.local/bin`.** Test: run `worker-run` on one issue and look for `agent-skills issue` in its log.
- [ ] **The default brief stays small.** Test: `agent-skills issue 107` in urchin (its body is over 12k characters) stays under about 4k characters.
- [ ] **An upstream merge costs minutes.** Test: merge the next upstream release and count the conflicts.

## Trial results (slice 1, 2026-11-15)

Six blender sessions ran after the slice 1 merges: 3 builds and 3 reviews. The counts come from `audit.py`, `openers.py` and `targets.py` in `~/tmp/2026-11-15-agent-cli-audit/`, with the output in its `trial/` folder.

| Session | Stage | Bash calls | Before the first source read | Raw `gh issue view` | Tail-only reruns |
|---|---|---|---|---|---|
| `ed3335d7` (`local_164fb59c`) | build #73 | 21 | 2 | 1 (blocked) | 0 |
| `7f4ce06f` (`local_21dde977`) | review PR 77 | 25 | 2 | 2 | 0 |
| `6d3ac9a0` (`local_ecb5e47b`) | build #74 | 41 | 4 | 0 | 0 |
| `1580f836` (`local_515a070a`) | build #31 | 53 | 2 | 0 | 0 |
| `7075996d` (`local_0da34974`) | review PR 79 | 37 | 4 | 0 | 0 |
| `355612a2` (`local_2c4a9a38`) | review PR 78 | 11 | 3 | 0 | 0 |

A source read is the first read of a file under `src/` or `tests/`, or the first `git diff` in a review. A tail-only rerun is the same command with only its `tail` or `head` changed and no edit between the two runs.

- **At most 1 Bash call before the first source read: missed.** Every session used 2 to 4 calls. The first call always reads `docs/agents/workflow.md`, because the agent file says to read it before any stage. The second reads the issue or the PR with `agent-skills issue` or `agent-skills pr`. The other calls read the spec, a research doc, or the linked-session note that the desktop app adds. So 2 calls is the floor with the current `workflow.md` rule. The verbs did replace the 3 to 6 `gh` calls of the old openers.
- **0 raw `gh issue view` calls: missed.** There were 3 calls in 2 sessions. In build #73, the hook blocked `gh issue view 73 --comments`, and the next call used `agent-skills issue 73`. Review PR 77 called `gh issue view 73 --json body --jq .body` twice. The hook allows that form. It also called `gh pr view 77 --json ...` after `agent-skills pr 77`. The PR brief already holds the commits and the files, but the reviewer piped it through `head -80` (evidence: its second call). The issue calls read the whole body, which `agent-skills issue` cuts at 2,000 characters without `--full`.
- **0 tail-only test reruns: met.** Review PR 79 ran `prek run --all-files` twice with `tail -30` and `tail -14`, but it edited files between the two runs.
- **Verb use:** 53 calls in 6 sessions. `run` 33, `issue` 7, `claim` 5, `pr` 3, `next-cmd` 3, `frontier` 1, `--help` 1. Of 40 test, lint and type-check runs, 31 went through `agent-skills run`. The agents still piped 9 of the wrapped runs to `tail`, which the wrapper makes unnecessary.

For slice 2, this suggests:

- Put the `workflow.md` rules that a stage needs into the stage brief, so the first call can be the brief. This is [spec/helpers-stage-brief.md](../../spec/helpers-stage-brief.md).
- Tell agents to read the whole `agent-skills pr` output, and to use `--full` for the whole issue body.
- Tell agents in the `run` section that the summary already holds the tail, so no `| tail` is needed.

## Trial results (slice 2, 2026-11-15)

Six urchin sessions ran after the `agent-skills brief` merges: 4 builds and 2 reviews. Blender had no task ready to build. The counts come from `targets.py` in `~/tmp/2026-11-15-agent-cli-audit/`, run with `SOURCE_DIRS='scripts|test|spec|scenes|dev'`, because urchin keeps its code in those folders and not in `src/`. A source read is also the first `git diff` or `gh pr diff`.

| Session | Stage | Brief version | Bash calls | Before the first source read | Whole `workflow.md` reads | Raw `gh issue view` | Tail-only reruns |
|---|---|---|---|---|---|---|---|
| `120882cc` (`local_4c9adbe0`) | build #186 | first | 13 | 4 | 1 | 0 | 0 |
| `b9440472` (`local_4c9adbe0`) | build #188 | first | 29 | 6 | 1 | 0 | 0 |
| `abd7a5f5` (`local_4c9adbe0`) | build #189 | first | 77 | 4 | 1 | 0 | 0 |
| `affeb6f2` | build #204 | fixed | 30 | 3 | 0 | 0 | 0 |
| `83fe1bea` | review PR 278 | fixed, no task part | 23 | 3 | 0 | 0 | 0 |
| `305393dc` | review PR 285 | fixed, with task part | 19 | 1 | 0 | 0 | 0 |

The three first builds ran in one session, with the context cleared between runs. The #188 prompt also asked for a fresh branch and worktree, which added worktree calls.

The first three builds found two problems, which were fixed before the other three sessions:

- **The brief cut the newest comment at 600 characters.** In urchin the newest comment is often the long "Agent Brief". All three builds said the brief "got cut off" and ran `agent-skills issue <n> --full`. The brief now prints that comment whole.
- **Every build read all of `workflow.md`.** The `AGENTS.md` line said "Read all of `docs/agents/workflow.md` before other work in this repo". The #189 session named that line as its reason (evidence). The other two sessions gave no reason (guess). The brief header now says not to read the file, and urchin #284 and blender #81 changed the `AGENTS.md` line.

Then the review of PR 278 ran `agent-skills issue 273 --full`, because the review brief named the task but did not print it. The review brief now prints the task issue before the PR.

- **At most 1 Bash call before the first source read: met in 1 of 3 fixed sessions.** The review of PR 285 met it. Build #204 used `brief`, `claim` and `papercut find`. `claim` is a required step before code, and `papercut find` comes from the user's `CLAUDE.md`. So 2 calls is the floor for a build. The review of PR 278 used `brief`, `gh pr checkout` and `agent-skills issue`, and the task part now removes the third call.
- **0 whole `workflow.md` reads: met** after the fix, against 1 in each first build.
- **0 raw `gh issue view` calls: met** in all six sessions.
- **0 tail-only test reruns: met** in all six sessions.

## Not Doing (and Why)

- **An MCP server:** each tool schema loads into every session, and the GitHub MCP already exists. A script costs nothing until an agent calls it.
- **Wrappers for `rg`, `head`, `sed` and `cat`:** they are most of the calls, but each call is different. A wrapper removes no decision.
- **A git orientation verb:** each `git status`/`log`/`diff` form is one short call, so a wrapper saves little. `pr N` covers review.
- **Files mode in `next`:** none of the three repos runs the stages in files mode now.
- **Stage helpers for bustin-out-recomp:** it runs superpowers plans, not the agent-skills stages. It gets only the per-repo work in slice 2.
- **Upstream PRs:** you chose to diverge.

## Open Questions

- **Rename the moved skills** to `/agent-skills:next` and `/agent-skills:setup-workflow`? Under the plugin name, the current names become `/agent-skills:agent-skills-next`. The seeded `workflow.md` in urchin and blender names `/agent-skills-next`, so a rename means running setup again in both repos.
- **How do other machines get the fork?** Option 1: chezmoi external into `~/code/agent-skills` with `--ff-only` pulls. Option 2: keep the clone at `~/.local/share/agent-skills`.
- **Where does `run` keep its logs?** Option 1: `$TMPDIR/agent-skills/runs/`. Option 2: a git-ignored `tasks/logs/` in the repo.
