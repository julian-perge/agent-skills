# Tasks: agent-skills helpers, slice 1

Source spec: spec/helpers-map.md. Plan: [tasks/plan.md](plan.md).

Shared commands (from the map):

```
Unit tests:   PYTHONPATH=scripts python3 -m unittest discover -s scripts/agent_skills/tests
Fork checks:  node scripts/validate-skills.js && node scripts/validate-commands.js && node scripts/validate-reference-links.js && node scripts/validate-artifact-paths.js && node scripts/run-evals.js --min-rank1 95
Plugin check: claude plugin validate .
```

## Phase 1: install (spec/helpers-install.md)

- [x] **Task 1: Fork plugin source and the `next` command**
  - Description: Point the marketplace's plugin entry at the checkout. Add `/agent-skills:next`, whose body is today's `agent-skills-next` rules, with the setup command renamed.
  - Acceptance:
    - `.claude-plugin/marketplace.json` has the plugin `source` `"./"`, and the marketplace name stays `addy-agent-skills`.
    - `next` exists in all three command directories, with one `description`.
  - Verify: the fork checks and the plugin check pass.
  - Dependencies: none.
  - Files: `.claude-plugin/marketplace.json`, `.claude/commands/next.md`, `.gemini/commands/next.toml`, `commands/next.toml`.
  - Scope: S.

- [x] **Task 2: Switch every host to the checkout (riskiest task)**
  - Result (2026-11-15):
    - The settings change alone left the plugin "added but ignored". `claude plugin marketplace add ~/code/agent-skills` re-registered it with no remove step, and `claude plugin list` now shows "Read from: /Users/sweetjp/code/agent-skills".
    - Codex copies the plugin into `~/.codex/plugins/cache/agent-skills/agent-skills/<version>/`. `codex plugin add agent-skills@agent-skills` copies it again, also at the same version, so an edit reaches Codex only after that command.
    - The live `~/.claude/settings.json` got the one entry by hand, because `chezmoi apply` would also revert 9 other live settings that drifted from the template.
  - Description: Change the dotfiles templates so that Claude Code, OpenCode and the shell use `~/code/agent-skills`. Then do the steps outside both repos: edit Codex's config, run `chezmoi apply`, and re-register the marketplace only if needed and only after the user says yes.
  - Acceptance:
    - `jq '."addy-agent-skills".source' ~/.claude/plugins/known_marketplaces.json` shows `directory` with `/Users/sweetjp/code/agent-skills`.
    - In a new Claude Code session, `/agent-skills:next` exists. An edit to `next.md` appears after `/reload-plugins`.
    - Codex lists the agent-skills skills from the local source, and its cache behavior is written down. The generated OpenCode config names `~/code/agent-skills/skills`. `readlink ~/.local/bin/agent-skills` gives the fork's `bin/agent-skills`.
  - Verify: the commands above, plus `chezmoi execute-template < .chezmoiexternal.toml` shows no agent-skills entry on this Mac.
  - Dependencies: 1.
  - Files: dotfiles `dot_claude/settings.json.tmpl`, `dot_config/opencode/opencode.jsonc.tmpl`, `.chezmoiexternal.toml`, `dot_local/bin/symlink_agent-skills.tmpl`. Outside the repos: `~/.codex/config.toml`.
  - Scope: M.

### Checkpoint A: after tasks 1 and 2

- [ ] All three hosts and the shell read `~/code/agent-skills`.
- [ ] Review the Codex cache finding with the user before going on.

- [ ] **Task 3: Move the workflow seeds into the fork**
  - Description: Copy the 4 seed files to `references/workflow/`. Change the skill search path in `survey-prompt.md` to `~/code/agent-skills`, and the next-command name in `workflow-github.md` to `/agent-skills:next`.
  - Acceptance:
    - The 4 files exist, with only those changes compared with the dotfiles originals.
    - No file names `/agent-skills-next` or `~/.claude/plugins/cache/addy-agent-skills`.
  - Verify: the fork checks pass, and `rg` for the two old strings in `references/workflow/` finds nothing.
  - Dependencies: 1.
  - Files: `references/workflow/workflow-github.md`, `workflow-files.md`, `issue-tracker-github.md`, `survey-prompt.md`.
  - Scope: S.

- [ ] **Task 4: The `setup-workflow` command**
  - Description: Add `/agent-skills:setup-workflow`, whose body is today's setup SKILL.md body. Its seed links point at `${CLAUDE_PLUGIN_ROOT}/references/workflow/`, and it names `/agent-skills:next`.
  - Acceptance:
    - The command exists in all three directories with one `description`.
    - Every seed link in the body resolves to a file from task 3.
  - Verify: the fork checks pass. In a new Claude Code session, `/agent-skills:setup-workflow` loads, and its first step reads a seed file with no error.
  - Dependencies: 3.
  - Files: `.claude/commands/setup-workflow.md`, `.gemini/commands/setup-workflow.toml`, `commands/setup-workflow.toml`.
  - Scope: S.

- [ ] **Task 5: Fork agent files stop sending PRs upstream**
  - Description: Rewrite the scope note and the Pull Requests rules in `CLAUDE.md` and `AGENTS.md`. PRs target `julian-perge/agent-skills` `main`, and upstream comes in with `git fetch upstream && git merge upstream/main`.
  - Acceptance:
    - No rule tells an agent to open a PR against upstream, or to search upstream PRs first.
    - The merge instruction is present.
  - Verify: `rg -n -i upstream CLAUDE.md AGENTS.md` shows only the merge instruction.
  - Dependencies: none.
  - Files: `CLAUDE.md`, `AGENTS.md`.
  - Scope: XS.

- [ ] **Task 6: Delete the dotfiles copies**
  - Description: Delete the two skill folders and their three symlinks from dotfiles. Update the README and the workflow runbook to the new command names and path.
  - Acceptance:
    - The leftover-refs `rg` from `spec/helpers-install.md` finds no hit in a live file.
    - `chezmoi apply` leaves no dangling skill symlink in `~/.claude/skills` or `~/.agents/skills`.
  - Verify: the leftover-refs command, plus `fd -u -t l . ~/.claude/skills ~/.agents/skills -x test -e {}`.
  - Dependencies: 2, 4.
  - Files: dotfiles `skills/agent-skills-next/`, `skills/setup-agent-skills-workflow/`, `dot_claude/skills/symlink_agent-skills-next.tmpl`, `dot_claude/skills/symlink_setup-agent-skills-workflow.tmpl`, `dot_agents/skills/symlink_setup-agent-skills-workflow`, `README.md`, `private_obsidian/AI Runbooks/agent-skills workflow guide.md`.
  - Scope: S.

### Checkpoint B: install complete

- [ ] Success criteria 1 to 9 of `spec/helpers-install.md` hold.
- [ ] Ask the user before deleting `~/.local/share/agent-skills`.

## Phase 2: tracker-cli (spec/helpers-tracker-cli.md)

- [ ] **Task 7: CLI skeleton and CI step**
  - Description: Add the launcher, the argparse dispatch with exit codes 0, 1 and 2, the runner in `github.py` (owner and repo parsed from `origin`, `--repo` added to every `gh` call, GraphQL helper) and the fake runner for tests. Add the unit-test step to CI.
  - Acceptance:
    - `bin/agent-skills --help` works through a symlink.
    - Tests cover HTTPS and SSH `origin` forms, `--repo` on every recorded call, the exit code with no `gh`, and the exit code outside a repo.
  - Verify: the unit tests pass, and `~/.local/bin/agent-skills --help` works.
  - Dependencies: none.
  - Files: `bin/agent-skills`, `scripts/agent_skills/__init__.py`, `scripts/agent_skills/cli.py`, `scripts/agent_skills/github.py`, `scripts/agent_skills/tests/test_github.py`, `.github/workflows/test-plugin-install.yml`.
  - Scope: M.

- [ ] **Task 8: `frontier`**
  - Description: Add the frontier rule, the table output and the verb.
  - Acceptance:
    - The lowest open sub-issue with no open blocker and no assignee is the frontier.
    - `Frontier: none (<reason>)` appears when every open sub-issue is blocked or assigned, and when there are none. Exit 0 in each case.
  - Verify: the unit tests pass (rule cases plus a golden output), and a manual `agent-skills frontier 107` in urchin works.
  - Dependencies: 7.
  - Files: `scripts/agent_skills/tracker.py`, `render.py`, `cli.py`, `tests/test_frontier.py`, `tests/fixtures/frontier-*.json`.
  - Scope: S.

- [ ] **Task 9: `issue`**
  - Description: Add the issue query, the three spec-lookup rules, the cut limits, `--full` and the brief output.
  - Acceptance:
    - Each spec rule, several candidates, and no spec are covered by tests.
    - The cut marker appears with the counts.
    - `agent-skills issue 107` in urchin prints at most 5,000 characters, and `--full` prints everything.
  - Verify: the unit tests pass (golden output for one blender issue and for urchin#107), and the manual size check passes.
  - Dependencies: 8.
  - Files: `scripts/agent_skills/tracker.py`, `render.py`, `github.py`, `tests/test_issue.py`, `tests/fixtures/issue-*.json`.
  - Scope: M.

### Checkpoint C: after tasks 7 to 9

- [ ] The unit tests pass locally and in CI on a pushed branch.
- [ ] Manual `issue` and `frontier` runs in urchin and blender look right to the user.

- [ ] **Task 10: `pr`**
  - Description: Add the PR query, the task lookup (closing references, then `Closes #n`, then the branch number as a guess), the standard file, the output and the review line.
  - Acceptance:
    - Each task source and "no task" are covered by tests.
    - The review line leaves out each part that has no value.
    - For an open blender PR, the review line works in `/agent-skills:review` with no edit.
  - Verify: the unit tests pass, and the manual blender check passes.
  - Dependencies: 9.
  - Files: `scripts/agent_skills/tracker.py`, `render.py`, `github.py`, `tests/test_pr.py`, `tests/fixtures/pr-*.json`.
  - Scope: M.

- [ ] **Task 11: `next-cmd`**
  - Description: Add the four stages from the spec table, each printing one line, with exit 1 in the listed cases.
  - Acceptance:
    - Each stage prints the expected line from fixtures.
    - `build` with no frontier and `plan` with no spec exit 1.
  - Verify: the unit tests pass.
  - Dependencies: 8, 9, 10.
  - Files: `scripts/agent_skills/cli.py`, `render.py`, `tests/test_next_cmd.py`.
  - Scope: S.

- [ ] **Task 12: `claim`**
  - Description: Add the preconditions, the type and slug rules, the assign step, the branch step from `origin/<default>`, and the `--no-branch` and `--no-assign` flags.
  - Acceptance:
    - A closed issue, an issue assigned to someone else, a blocked issue, a dirty tree and an existing branch each exit 1 and record no write.
    - The success path records exactly the assign call and the two git calls.
  - Verify: the unit tests pass. One manual claim runs on a throwaway issue in a test branch, and the user approves the issue first.
  - Dependencies: 9.
  - Files: `scripts/agent_skills/tracker.py`, `github.py`, `cli.py`, `tests/test_claim.py`.
  - Scope: M.

- [ ] **Task 13: `next` rules**
  - Description: Port the group rules (Review, Build, Plan, Spec, Idea), the priority order, the frontier mark and the guess list into pure functions.
  - Acceptance: one test per row of the group table in the old SKILL.md, plus the priority order when an issue fits several groups.
  - Verify: the unit tests pass.
  - Dependencies: 8, 9.
  - Files: `scripts/agent_skills/tracker.py`, `tests/test_next_groups.py`.
  - Scope: S.

- [ ] **Task 14: `next` fetch and report**
  - Description: Add the paged issue query, the open-PR list, the sub-issue bodies for Plan candidates, the preflight and the report.
  - Acceptance:
    - The golden output matches for a recorded blender tracker state.
    - Two live runs with no tracker change give the same output byte for byte.
    - Preflight exits 2 with the old messages.
  - Verify: the unit tests pass, and two manual runs in blender are compared with `cmp`.
  - Dependencies: 13.
  - Files: `scripts/agent_skills/github.py`, `render.py`, `cli.py`, `tests/test_next.py`, `tests/fixtures/next-*.json`.
  - Scope: M.

### Checkpoint D: tracker-cli complete

- [ ] Success criteria 1 to 8 of `spec/helpers-tracker-cli.md` hold.
- [ ] Review the CLI output with the user before the stage files name it.

## Phase 3: run-wrapper (spec/helpers-run-wrapper.md)

- [ ] **Task 15: `run` process mechanics**
  - Description: Add the argv execution, the log path, the ANSI-free log written as output arrives, the `log:` first line, the exit-code rules (pass-through, 125, 127, `128 + n`) and the signal forwarding.
  - Acceptance:
    - Spec criteria 2 to 4 hold.
    - The log can be read while the child still runs.
  - Verify: the unit tests pass (tests with `python3 -c` children).
  - Dependencies: 7.
  - Files: `scripts/agent_skills/run.py`, `cli.py`, `tests/test_run.py`.
  - Scope: M.

- [ ] **Task 16: `run` summary patterns**
  - Description: Add the fixed pattern table, the cap of 40 lines with no duplicates, and the `--tail` section.
  - Acceptance: spec criterion 1 holds for the four real fixtures.
  - Verify: the unit tests pass. A manual `agent-skills run` of `test-blender.sh -k pick` in blender needs no second run.
  - Dependencies: 15.
  - Files: `scripts/agent_skills/run.py`, `tests/test_run_summary.py`, `tests/fixtures/run/`.
  - Scope: S.

### Checkpoint E: run-wrapper complete

- [ ] Success criteria 1 to 5 of `spec/helpers-run-wrapper.md` hold.

## Phase 4: stage-wiring (spec/helpers-stage-wiring.md)

- [ ] **Task 17: Stage commands name the verbs**
  - Description: Add one sentence each to `build.md`, `review.md`, `plan.md` and `spec.md`, worded as in the spec. Replace the `next.md` body with "run `agent-skills next` and print its output".
  - Acceptance:
    - Each file names the verbs that the spec lists for it.
    - `/agent-skills:next` in blender prints the same as `agent-skills next`.
  - Verify: the fork checks pass, plus the `rg` per verb from the spec and the manual blender comparison.
  - Dependencies: 1, 10, 11, 12, 14, 16.
  - Files: `.claude/commands/build.md`, `review.md`, `plan.md`, `spec.md`, `next.md`.
  - Scope: S.

- [ ] **Task 18: Workflow seeds name the verbs**
  - Description: Add the `## Helpers` section and the Build, Review and verify changes to `workflow-github.md`. Make reads use verbs in `issue-tracker-github.md`. Add the `run` line to `workflow-files.md`. Add the stale rule and the `command -v agent-skills` check to `setup-workflow.md`.
  - Acceptance: every change listed in items 3 to 6 of the spec is present.
  - Verify: the fork checks pass, plus an `rg` for `## Helpers` and for each verb.
  - Dependencies: 4, 11, 12, 16.
  - Files: `references/workflow/workflow-github.md`, `issue-tracker-github.md`, `workflow-files.md`, `.claude/commands/setup-workflow.md`.
  - Scope: S.

- [ ] **Task 19: Hook rules in dotfiles**
  - Description: Unwrap `agent-skills run` in `enforce-tools.sh`, add Rule A and Rule B, and add the cases script with the spec's table.
  - Acceptance:
    - Every case in the table gives its expected exit through the Claude Code hook path and the Codex hook path.
    - One blocked `gh issue view 5 --comments` in an OpenCode worker session.
  - Verify: the cases script exits 0, and the manual OpenCode check passes.
  - Dependencies: 9, 10, 15.
  - Files: dotfiles `dot_claude/hooks/executable_enforce-tools.sh`, `dot_claude/hooks/enforce-tools-cases.sh`.
  - Scope: S.

### Checkpoint F: before touching other repos

- [ ] Success criteria 1, 2 and 4 of `spec/helpers-stage-wiring.md` hold.
- [ ] The user approves opening the urchin and blender PRs.

- [ ] **Task 20: Refresh urchin and blender workflow docs**
  - Description: Run `/agent-skills:setup-workflow` in each repo and open one PR per repo. The user merges.
  - Acceptance:
    - Each `workflow.md` has `## Helpers` and keeps its owner text.
    - Each `issue-tracker.md` uses the verbs for reads.
  - Verify: the PR diff in each repo, and the setup command's own step 6 checks.
  - Dependencies: 17, 18, 6.
  - Files: urchin and blender `docs/agents/workflow.md` and `docs/agents/issue-tracker.md`.
  - Scope: S.

- [ ] **Task 21: Measure the core bet**
  - Description: After both PRs merge, the user runs 3 build sessions and 2 review sessions in blender. Run `audit.py` and `openers.py` over those sessions and write the numbers into the idea doc.
  - Acceptance:
    - At most 1 Bash call before the first source read.
    - 0 raw `gh issue view` calls.
    - 0 test reruns that differ only in the `tail` length.
    - A miss is recorded with its numbers, not hidden.
  - Verify: the numbers and the session ids are in `docs/ideas/agent-skills-helpers.md`.
  - Dependencies: 19, 20.
  - Files: `docs/ideas/agent-skills-helpers.md`.
  - Scope: XS.

### Checkpoint G: slice 1 complete

- [ ] Every success criterion in the four module specs holds.
- [ ] The measurement decides what slice 2 does first.
