---
description: "Set up this repo for the /agent-skills workflow (idea, interview, spec, plan, build, review), or migrate it there from mattpocock-skills. Safe to re-run."
disable-model-invocation: true
---

# Setup agent-skills workflow

Give a repo the `agent-skills` stages with no other skill plugin in the loop. Tasks are GitHub issues with labels (the tracker mode of `planning-and-task-breakdown`), specs are files under `spec/`, and ADRs stay in `docs/adr/`.

This is a prompt-driven command. Explore, build a **gap table**, confirm, write, verify. The repo may be blank, half set up, or set up for `mattpocock-skills`. Every artifact is classified, so a re-run changes only what is not **current**.

## Process

### 1. Preflight

Stop and tell the user when `agent-skills` is not enabled (`enabledPlugins` in `~/.claude/settings.json` or the repo's `.claude/settings*.json`).

### 2. Explore

Read the repo. Do not assume.

- **Tracker**: `gh repo view --json nameWithOwner,isFork,hasIssuesEnabled,parent` and `gh label list`. A fork can have issues off. `.scratch/` with spec and ticket files means the repo tracks work in local files today.
- **Agent file**: which of `CLAUDE.md` and `AGENTS.md` exist, whether `CLAUDE.md` is only `@AGENTS.md`, and whether it holds a `## Workflow` block, an old `## Agent skills` block, or both.
- **`docs/agents/`**: which of `workflow.md`, `issue-tracker.md`, `triage-labels.md` and `domain.md` exist. Diff each old file against its seed (`fd -u setup-matt-pocock-skills ~/.claude/plugins/cache`) to find the lines the repo's owner wrote. Those lines are **owner text** and must survive.
- **Convention evidence**: the last five merged PR titles and branch names (`gh pr list --state merged --limit 5`, `git branch -r`), `git log --oneline -15`, and any rule in a roadmap or parent issue about branches, PRs or reviews. These beat the defaults in the templates.
- **Verify command**: `package.json` scripts, `pyproject.toml`, `prek.toml`, `Makefile`, `justfile`, and any "Every task" or "Build" lines in the agent file.
- **Domain docs**: whether `GLOSSARY.md`, `docs/adr/` and `CODING_STANDARDS.md` exist. Create none of them.
- **Old workflow in live docs**: `rg -uu -n -e 'mattpocock-skills|/to-spec|/to-tickets|implement-spec|grill-with-docs|/wayfinder|/triage|/domain-modeling|\bcode-review\b' AGENTS.md CLAUDE.md docs/agents` (skip the paths that do not exist). Also search code and scripts for helpers of the old flow, and report them without changing them.
- **Open wayfinder work**: `gh issue list --state open --label wayfinder:map` and any open `wayfinder:*` issue.

Build the gap table. One row per artifact, one state per row:

| Artifact | States |
|---|---|
| Agent file `## Workflow` block | missing, current, stale (an `## Agent skills` block still exists, or the block says "Read `docs/agents/workflow.md` before any `/agent-skills` command.", or it says "Read all of `docs/agents/workflow.md` before other work in this repo." with no "do not read that file in a stage") |
| Agent file `## Every task` verify line | missing, current |
| `docs/agents/workflow.md` | missing, current, stale (names old stage skills, says specs live in issues, or has no rule that a stage ends by printing the next command with real values, or GitHub mode has no `## Helpers` section, or says "Report every guess and every gap you accepted" with no `agent-skills decide`, or says `tasks/plan.md` holds the plan's decisions, or GitHub mode has no rule about closing keywords under Reports, or its `auto` pull request does not close the source issue), foreign (owner-written, different shape) |
| `docs/agents/issue-tracker.md` | missing, current, stale (still has the triage, "When a skill says" or wayfinding sections, reads issues with raw `gh` where the seed names an `agent-skills` verb, or has a frontier query without the `ready-for-agent` condition) |
| `docs/agents/triage-labels.md`, `docs/agents/domain.md` | absent, present (to fold and delete) |
| `tasks/` in `.gitignore` | missing, current |
| The five labels on the tracker | missing (name them), current |
| Open wayfinder issues | none, found (list them) |

### 3. Ask

First print the gap table with one line of evidence per row. Then one `AskUserQuestion` call, up to four questions. Ask only what exploration left open. Recommended answer first.

- **Tracker mode**: GitHub issues (recommended when the remote is GitHub), or files (`tasks/todo.md`, the `agent-skills` default). A fork with issues off needs `gh repo edit --enable-issues` for the first answer. A repo that tracks work in `.scratch/` today has no recommended answer: ask.
- **No agent file**: create `AGENTS.md` plus a `CLAUDE.md` holding `@AGENTS.md` (recommended), or `CLAUDE.md` alone.
- **No verify command found, or several**: which single command proves a change? Offer the candidates found.
- **Open wayfinder issues found**: leave them and keep `mattpocock-skills` enabled until they close (recommended), or convert them now. Converting means the user settles each open decision ticket with `/agent-skills:interview-me`, then runs `/agent-skills:spec` with a capability map. This command converts nothing itself.

### 4. Draft and confirm

Show every row that is not **current** as the exact edit: a diff for existing files, full text for new ones, and the name of each file to delete with the owner text it carries and where that text goes. Then ask with `AskUserQuestion`: write as shown (recommended), or change first. Write nothing until the user answers. This step is done when that answer is in.

### 5. Write

Rules for every edit: edit the existing file; update a block in place; keep owner text.

- **Agent file**: replace the whole `## Agent skills` block with the block below, or add the block when there is none.

  ```markdown
  ## Workflow

  - Tasks are tracked in GitHub Issues for <owner>/<repo>, with the `gh` CLI. `/agent-skills:plan` creates one sub-issue per task. `tasks/` is git-ignored scratch.
  - Specs are files at `spec/<issue>-<slug>.md`, not `SPEC.md`.
  - ADRs go in `docs/adr/`. Read `GLOSSARY.md` and `docs/adr/` (those that exist) before design work.
  - Start each `/agent-skills` stage with `agent-skills brief <stage> <n>`. It prints every rule of `docs/agents/workflow.md` that the stage needs, so do not read that file in a stage. Before other work in this repo, read all of `docs/agents/workflow.md`.
  ```

  Files mode: the first bullet becomes "Tasks are tracked in `tasks/todo.md`, and `tasks/` is committed." and the spec path is `spec/<slug>.md`.

  When the agent file has no verify line, add a `## Every task` section above `## Workflow` with one line naming the verify command. The verify command lives only in the agent file.
- **`docs/agents/workflow.md`**: seed from `${CLAUDE_PLUGIN_ROOT}/references/workflow/workflow-github.md` or `${CLAUDE_PLUGIN_ROOT}/references/workflow/workflow-files.md`. Replace the template defaults (branch names, PR title form, one PR per task or per spec) with the convention evidence. Change nothing else in a seeded file. For a **stale** or **foreign** file, rewrite these parts to the template's and keep the owner text, each rule under the stage it belongs to: the "The user types each stage" paragraph, the `## Helpers` section (GitHub mode), the stage table, the task body line and the `tasks/plan.md` line under Plan, the frontier, claim, `Closes` and verify lines and the review command under Build, the Review section, and the Reports section.
- **`docs/agents/issue-tracker.md`** (GitHub mode): when missing, seed from `${CLAUDE_PLUGIN_ROOT}/references/workflow/issue-tracker-github.md`. When stale, delete the sections "Pull requests as a triage surface", "When a skill says ..." and "Wayfinding operations", and keep their blocking, frontier and claim bullets under a `## Sub-issues and blocking` heading, with "map" reworded to "parent issue". Rewrite the Conventions bullets and the frontier and claim bullets from the seed, so reads use the `agent-skills` verbs and the frontier needs `ready-for-agent`. Keep owner text. Leave the wayfinding section in place when the user chose to keep open wayfinder issues.
- **`docs/agents/triage-labels.md` and `docs/agents/domain.md`**: move their owner text into `workflow.md` (label overrides under Labels, domain rules under Design), then delete both files. Keep `triage-labels.md` when the user chose to keep open wayfinder issues.
- **`.gitignore`** (GitHub mode): add `tasks/`.
- **Labels** (GitHub mode): `gh label create` for each missing one of `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`.
- **Old workflow in live docs**: swap each old stage skill for its stage in the template's table. Leave history (`docs/research/`, `docs/superpowers/`, `.superpowers/`, `.recall/`, closed tickets) alone.

### 6. Verify

Done when all five hold. Run them; do not assume.

1. The old-workflow `rg` from step 2 returns no hit in live docs, except the files the user chose to keep for open wayfinder issues.
2. Every path named in the agent file's `## Workflow` block and linked from `workflow.md` exists, except `GLOSSARY.md`, `docs/adr/` and `spec/`, which appear when first used.
3. `git status --short` lists only the files this command meant to change.
4. GitHub mode: `gh repo view --json nameWithOwner` names the user's own repo, and every label exists.
5. `command -v agent-skills` prints a path, so the verbs that `workflow.md` names can run.

### 7. Done

Report one table: each artifact, and **written**, **deleted**, **left** or **declined**. Then:

- Existing `ready-for-agent` issues stay valid. Report the sections they lack, such as a verification line or a `Spec` line, and convert nothing.
- GitHub mode: tell the user that `/agent-skills:next` lists the PRs to review, the tasks to build and the issues to spec or plan, each with the command to paste.
- Name the open wayfinder issues, the old-flow helper scripts and any issue text that names an old skill. The user decides each one.
- Name the two unproven parts, for the user to dry-run on one small feature: `/agent-skills:plan` creating sub-issues, and `/agent-skills:build auto` running tracker tasks.
- Tell the user the last step, to do by hand after three issues pass through the new flow and no wayfinder issue is open: set `"mattpocock-skills@claude-plugins-official": false` under `enabledPlugins` in the repo's `.claude/settings.json`. Say that it is unverified that a project-level `false` overrides a user-level `true`.
- Print the survey prompt from `${CLAUDE_PLUGIN_ROOT}/references/workflow/survey-prompt.md`.
