# Survey prompt

Print this block in step 7 of the skill, unchanged. It finds the repo and the skill files by itself. It is for GitHub mode. In files mode, tell the user to read `tasks/todo.md` instead.

````
List every open issue in this repo and recommend a next step for each. Change nothing until step 6.

1. Get the repo with `gh repo view --json nameWithOwner`. Fetch the issues with `gh issue list --state open --limit 200 --json number,title,labels,body,milestone,createdAt`. Read the sub-issue and blocking links of every parent issue. Read the labels, the bodies, `spec/`, and GLOSSARY.md and docs/adr/ if they exist. Do not guess from titles alone.

2. Read these files to learn what each step is for:
   - SKILL.md of `idea-refine`, `interview-me`, `spec-driven-development`, `planning-and-task-breakdown`, `incremental-implementation`, `test-driven-development` and `documentation-and-adrs`, and the `spec`, `plan`, `build`, `test` and `review` command files. Find them with `fd -u -e md . ~/code/agent-skills`.
   - The "Workflow" section of AGENTS.md and docs/agents/workflow.md.

3. For each issue, pick one recommendation and give a one-line reason from its text:
   - label only: the issue lacks a triage label or has the wrong one. Name the label.
   - /agent-skills:idea-refine: the goal itself is vague.
   - /agent-skills:interview-me: the problem is known, but the design is not settled. Add "then ADR" if a decision must be recorded.
   - /agent-skills:spec: the design is settled, no file under spec/ covers it, and the work needs more than one task. Say "with capability map" when it spans several independent parts.
   - /agent-skills:plan: a spec file exists and the issue has no task sub-issues.
   - /agent-skills:build: the issue is one task with acceptance criteria, no open blockers and the ready-for-agent label.
   - /agent-skills:test: a bug with a known reproduction and no failing test yet.
   - convert: an issue labelled `wayfinder:map` or `wayfinder:*`. Say what it becomes.
   Do not invent other steps for this column.

4. Output one table sorted by priority, highest first. Rank by: blocks other issues, then user-visible breakage, then the main roadmap, then polish. Columns: rank, number and title, current labels, proposed labels, recommended step, reason, blocked by. Get "blocked by" from `gh api repos/<owner>/<repo>/issues/<n>/dependencies/blocked_by`, not from prose. Put issues that belong together next to each other and name the group.

5. After the table, answer these questions:
   a. Which issues are ready for /agent-skills:spec now? Name the groups that one spec file would cover.
   b. Which issues are ready for /agent-skills:plan or /agent-skills:build now?
   c. Which issues need another step first? Name the step and the issue.
   d. Give the next 5 runs in order, each with the exact slash command and the issue numbers. Put each command in its own code block.

6. If the "proposed labels" column differs from the current labels for any issue, ask me once with AskUserQuestion whether to apply all, apply none, or let me pick. Apply only what I approve, with `gh issue edit`.

State conclusions directly. Mark any guess as a guess. Ask me about an issue only when it is truly unclear, using AskUserQuestion.
````
