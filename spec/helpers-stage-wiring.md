# Spec: stage-wiring, V1

Module of [helpers-map.md](helpers-map.md). It inherits the tech stack, commands, code style and boundaries there. It uses the verbs that [helpers-tracker-cli.md](helpers-tracker-cli.md) and [helpers-run-wrapper.md](helpers-run-wrapper.md) define, by name only.

## Objective

Every `/agent-skills` stage calls a verb on its first lookup and does not build its own `gh` call. Two hook rules block the `gh` forms that cost the most time. This module also tests the core bet of the whole idea: agents use a fixed helper when the instructions name it.

## Changes in the fork

1. **Stage commands.** Add one sentence below the `Invoke the ...` line of each file. Each sentence starts with "In a repo whose `docs/agents/workflow.md` tracks tasks in GitHub Issues,".
   - `.claude/commands/build.md`: "...start with `agent-skills issue <n>`, take the task with `agent-skills claim <n>`, run tests and checks with `agent-skills run --`, and end with the line that `agent-skills next-cmd review <pr>` prints."
   - `.claude/commands/review.md`: "...start with `agent-skills pr <pr>`, which names the task, the spec and the standard, and run tests with `agent-skills run --`."
   - `.claude/commands/plan.md`: "...start with `agent-skills issue <n>` and end with the line that `agent-skills next-cmd build <n>` prints."
   - `.claude/commands/spec.md`: "...start with `agent-skills issue <n>` and end with the line that `agent-skills next-cmd plan <n>` prints."
2. **`.claude/commands/next.md`.** The body becomes: run `agent-skills next` from the repo root and print its output unchanged. When it exits 2, print its message and stop. The command stays read-only. The rules now live in code and tests only.
3. **`references/workflow/workflow-github.md`.**
   - Add a `## Helpers` section that lists `issue`, `pr`, `claim`, `frontier`, `next-cmd`, `run` and `next`, each with its one-line purpose. Add the rule: when a verb covers a lookup, use the verb and do not write the `gh` call.
   - The Build section names `frontier` and `claim` instead of the raw frontier query and `gh issue edit`. It says that `next-cmd review <pr>` prints the review line.
   - The Review section names `agent-skills pr <pr>`.
   - The verify command runs through `agent-skills run --`.
4. **`references/workflow/issue-tracker-github.md`.** Reads use the verbs. Raw `gh` stays only for writes that no verb covers: creating a sub-issue, adding a `blocked_by` edge, labels and comments.
5. **`references/workflow/workflow-files.md`.** Add only the `agent-skills run --` line, because the other verbs need GitHub mode.
6. **`.claude/commands/setup-workflow.md`.**
   - A `workflow.md` without the `## Helpers` section counts as **stale** in the gap table.
   - Step 6 (verify) adds `command -v agent-skills`.
7. **Not edited:** `idea-refine` and `interview-me`. The repo's `workflow.md`, which every stage reads first, covers them.

## Changes in dotfiles

These changes go in `dot_claude/hooks/executable_enforce-tools.sh`. Claude Code runs this hook, Codex runs it through `~/.codex/hooks/enforce-tools.sh`, and OpenCode runs it through `plugins/enforce-tools.ts`. Each rule goes in the existing per-program `case`, so the hook's parser keeps quoted strings and heredoc bodies from firing it.

1. **Unwrap `agent-skills run`.** Add `agent-skills run [--name X] [--tail N] --` as one more wrapper layer, next to `env`, `timeout` and `xargs`. Every rule then applies to the wrapped command.
2. **Rule A.** `gh issue view` or `gh pr view` with `--comments` and without `--json` is blocked with: "`gh <issue|pr> view --comments` prints only the comments when stdout is not a terminal. Use `agent-skills issue <n>` or `agent-skills pr <n>`, or add `--json title,body,comments`."
3. **Rule B.** A `gh` write without `--repo` or `-R` is blocked when the current repo has an `upstream` remote. The writes are `issue create|edit|close|reopen|comment|delete|develop`, `pr create|edit|close|merge|ready|comment|review` and `label create|edit|delete`. The message: "This repo has an upstream remote, so gh can target the parent repo. Add `--repo <origin owner/repo>`." It names the real origin repo. `gh api` is not covered, because its path names the repo.

## Changes in urchin and blender-addon-rs317-667mqo-makeup

Run `/agent-skills:setup-workflow` in each repo. It marks `docs/agents/workflow.md` stale, rewrites it from the new seed with the owner text kept, and updates `issue-tracker.md`. Open one PR per repo. The user merges each one.

## Commands

```
Fork checks:  see helpers-map.md
Hook case:    printf '%s' '{"tool_input":{"command":"<cmd>"},"cwd":"<dir>"}' | ~/.claude/hooks/enforce-tools.sh; echo "exit $?"
Codex hook:   the same input piped into ~/.codex/hooks/enforce-tools.sh
Measurement:  ~/tmp/2026-11-15-agent-cli-audit/audit.py and openers.py, run on the sessions started after the merge
```

## Testing strategy

- **Hook:** the table of cases below, run with the hook-case command for each hook path. Dotfiles has no test harness for the hook, so the build adds the cases as a script, `dot_claude/hooks/enforce-tools-cases.sh`, that prints one line per case and exits non-zero on any mismatch.
- **Docs:** the fork checks, plus an `rg` for each verb name in the edited files.
- **Behavior:** the measurement in success criterion 5.

| Command | cwd | Expected exit |
| --- | --- | --- |
| `gh issue view 5 --comments` | urchin | 2 |
| `gh issue view 5 --comments --json title,body,comments` | urchin | 0 |
| `echo "gh issue view 5 --comments"` | urchin | 0 |
| `gh pr view 9 --comments` | urchin | 2 |
| `gh issue edit 5 --add-assignee @me` | `~/code/agent-skills` (has `upstream`) | 2 |
| `gh issue edit 5 --repo julian-perge/agent-skills --add-assignee @me` | `~/code/agent-skills` | 0 |
| `gh issue edit 5 --add-assignee @me` | urchin (no `upstream`) | 0 |
| `agent-skills run -- pre-commit run` | urchin | 2 (the existing prek rule) |

## Success criteria

1. The fork checks pass. Each verb named in "Changes in the fork" appears in the file that the change lists.
2. Every case in the hook table gives its expected exit through `~/.claude/hooks/enforce-tools.sh` and `~/.codex/hooks/enforce-tools.sh`. In one OpenCode worker session, `gh issue view 5 --comments` is blocked.
3. The `workflow.md` of urchin and of blender has the `## Helpers` section and keeps its owner text. Each change is in a PR.
4. The `/agent-skills:next` output in blender equals `agent-skills next` run directly.
5. **The core bet.** After the merges, run 3 build sessions and 2 review sessions in blender. `audit.py` and `openers.py` over those sessions must show:
   - At most 1 Bash call before the first read of a source file.
   - 0 raw `gh issue view` calls.
   - 0 test reruns that differ only in the `tail` length.

   Write the numbers into [docs/ideas/agent-skills-helpers.md](../docs/ideas/agent-skills-helpers.md).

## Boundaries

These add to the shared boundaries in the map.

- **Ask first:** opening the urchin and blender PRs. A hook rule other than A and B.
- **Never:** block a read-only `gh` command other than the Rule A case. Edit the `.gemini` or `commands/` bodies beyond their pointer text.

## Out of scope (deferred)

- **Slice 2:** the `UserPromptSubmit` brief injection, the `audit` verb, the per-repo `## Commands` table and the per-repo summary scripts.
- **Edits to `idea-refine` and `interview-me`:** `workflow.md` covers them.
- **Blocking `gh issue view --json`:** it works, so it stays allowed.

## Open questions

None.
