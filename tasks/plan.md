# Implementation Plan: agent-skills helpers, slice 1

Source spec: spec/helpers-map.md (module specs: spec/helpers-install.md, spec/helpers-tracker-cli.md, spec/helpers-run-wrapper.md, spec/helpers-stage-wiring.md)

Tasks are in [tasks/todo.md](todo.md). The task list below is an ordered index only, so the two files cannot drift apart.

## Overview

Slice 1 has four parts:
1. The fork at `~/code/agent-skills` becomes the one copy of the pack that every host uses.
2. The two dotfiles skills become fork commands.
3. A Python CLI, `agent-skills`, replaces the `gh` lookups and the test-output trimming that the audit found in stage sessions.
4. The stage commands, the workflow seeds and the `enforce-tools.sh` hook point agents at the CLI.

The last task measures whether agents use it.

## Architecture decisions

- **`next` and `setup-workflow` are commands, not skills.** Both are user-invoked only. As skills, they would need the skill-anatomy sections and routing evals for a path the model never takes. Codex and OpenCode run `agent-skills next` directly.
- **Claude Code uses a `directory` marketplace at `~/code/agent-skills`.** The docs say a relative-path plugin there loads in place, so an edit takes effect after `/reload-plugins`. The marketplace keeps the name `addy-agent-skills`, because `agent-skills` is a reserved name.
- **The CLI is a stdlib package with a launcher.** The code is `scripts/agent_skills/`, and the launcher `bin/agent-skills` is on PATH through the plugin `bin/` (Claude Code) and `~/.local/bin` (Codex, OpenCode).
- **One process boundary.** Only `github.py` runs `gh` or `git`. Tests replace its runner with a fake that serves recorded responses and records every call.
- **One GraphQL call per read verb.** The fields were checked against julian-perge/urchin#161 on 2026-11-15.
- **The `enforce-tools.sh` rules go in the existing per-program `case`.** `agent-skills run` becomes one more wrapper that the hook unwraps, so a wrapped command still meets the existing rules.

## Task list (index)

Phase 1, install: 1, 2, checkpoint A, 3, 4, 5, 6, checkpoint B.
Phase 2, tracker-cli: 7, 8, 9, checkpoint C, 10, 11, 12, 13, 14, checkpoint D.
Phase 3, run-wrapper: 15, 16, checkpoint E.
Phase 4, stage-wiring: 17, 18, 19, checkpoint F, 20, 21, checkpoint G.

Task 2 is the riskiest, so it comes second: it proves that all three hosts read the checkout before anything else depends on it.

## Parallel work

- Phase 1 and Phase 2 touch different files, so they can run in separate sessions.
- Phase 3 needs task 7 only.
- Phase 4 needs everything before it.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Claude Code keeps the old `github` registration after the settings change | Medium | Task 2 checks `known_marketplaces.json`. Re-adding the marketplace uninstalls the plugin and deletes its data, so it needs the user's yes first. |
| Codex copies a local plugin into its cache, so edits do not reach it | Medium | Task 2 measures this, and the refresh command goes into the fork's `AGENTS.md`. |
| Upstream merges conflict in the edited command files | Medium | Each stage-command edit is one sentence (task 17). |
| Agents keep writing their own `gh` calls (the core bet fails) | High | Rule A blocks the most common bad form. Task 21 measures the result, and its numbers decide slice 2 (for example the brief-injection hook). |
| `validate-artifact-paths.js` rejects the moved setup text | Low | Tasks 3 and 4 run the fork checks. |
| The summary patterns miss a failure line | Low | The log path is the first output line, so the agent reads the log and does not run the suite again. |
| The chezmoi external entry fails on Linux | Low | Checked on the next Linux `chezmoi apply`. |

## Open questions

- Commit `docs/ideas/`, `spec/` and `tasks/` before task 1? `/build auto` stops on untracked files that are not planning artifacts, and `docs/ideas/` is not one.
