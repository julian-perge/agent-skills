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

- [ ] **Agents call the verbs when the command file names them.** Test: after slice 1, run 3 build and 2 review sessions in blender, then run `audit.py`. Targets: 1 Bash call before the first source read, and 0 raw `gh issue view` calls.
- [ ] **Claude Code installs from a directory marketplace whose plugin source is `./`.** Test: check that `/agent-skills:build` resolves to `~/code/agent-skills` and not to the plugin cache.
- [ ] **The OpenCode workers and Codex see `~/.local/bin`.** Test: run `worker-run` on one issue and look for `agent-skills issue` in its log.
- [ ] **The default brief stays small.** Test: `agent-skills issue 107` in urchin (its body is over 12k characters) stays under about 4k characters.
- [ ] **An upstream merge costs minutes.** Test: merge the next upstream release and count the conflicts.

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
