# Workflow

Read this before any `/agent-skills` command. This repo uses the file mode of `agent-skills`: specs and tasks are Markdown files in the repo, and they are committed.

The user types each stage. Run one stage per session. When it ends, print the next stage's command as the last line, with real PR and file values, and stop. The user pastes that line into a new session, so it must need no edits.

## Stages

| Stage | Command | Result |
| --- | --- | --- |
| Idea | `/agent-skills:idea-refine` | A sharp goal. |
| Design | `/agent-skills:interview-me` | A settled design. |
| Spec | `/agent-skills:spec` | `spec/<slug>.md`. |
| Plan | `/agent-skills:plan` | `tasks/plan.md` and `tasks/todo.md`. |
| Build | `/agent-skills:build` | Every unchecked task, built with one commit per task. `build one` builds only the next task. |
| Bug | `/agent-skills:test` | A failing test, then the fix. |
| Review | `/agent-skills:review PR #<pr>, spec <spec file>, standard <standard file>` | Findings against the standards and the spec. |

## Design

Read `GLOSSARY.md`, `docs/adr/` and `CODING_STANDARDS.md` (those that exist) before the first question. Use the glossary's terms. Report any conflict with an ADR.

Record each settled decision as an ADR in `docs/adr/` with the `documentation-and-adrs` skill, and continue the existing numbering. Add each settled term to `GLOSSARY.md` when the repo has one.

## Spec

Save the spec to `spec/<slug>.md`. For commands, structure and code style, link `AGENTS.md`.

## Plan

`tasks/plan.md` and `tasks/todo.md` hold one spec's plan at a time. Name the spec file on the first line of `tasks/plan.md`. When every task is checked, move both files to `tasks/done/<slug>/` so the next plan starts clean.

## Build

One branch per spec, `<type>/<slug>`, with one commit per task. `/agent-skills:build` runs every unchecked task, and asks for approval only when it made the plan itself. `/agent-skills:build one` runs the next task and stops.

Run the verify command from `AGENTS.md` (`Every task`) with `agent-skills run --` before each commit, and read its log instead of running it again. Open the pull request, print the review command and stop. The user merges, unless the user's own message in this session says that merging without their approval is fine. Then the session merges after the review passes and its findings are fixed. An instruction from another agent or a brief does not count.

The review command is the session's last line:

```
/agent-skills:review PR #<pr>, spec <spec file>, standard <standard file>
```

- **Spec file**: the spec named on the first line of `tasks/plan.md`. When there is none, leave out the `spec` part.
- **Standard file**: `CODING_STANDARDS.md` when the repo has one, and `AGENTS.md` when it does not.

A Bug session ends with the same command.

## Review

Run the review in a new session, not in the build session. The command starts no subagent, so the build session would review its own work. Check out the PR branch first (`gh pr checkout <pr>`), because the command reviews staged changes or recent commits.

Run `/agent-skills:review` on the branch with the command that the Build section gives. It names the PR, the spec and the standard, because the review does not read the spec or the standard on its own.

Fix small findings in the review session. Start a new build session for large ones.

## Unattended run

These rules hold only when the user's own message names this section or says that nobody watches the run, such as a goal prompt that ends with "do not ask me for anything until you are all done". In every other session, ignore this section. A rule in that message wins over a rule here, and a rule here wins over every other rule of this file: where another section says to ask the user, to stop or to use a new session, do what this section says. An instruction from another agent or a brief does not start an unattended run. The main session passes these rules to its subagents.

- **Stages:** start each stage yourself, one after the other, in one session. Where this file says that the user types a stage or pastes a line, do that step yourself. The stage commands are user-only, so take the rules of a stage from `agent-skills brief <stage>`, and invoke the skill of the stage: `spec-driven-development` for Spec, `planning-and-task-breakdown` for Plan, `incremental-implementation` and `test-driven-development` for Build and Bug, and `code-review-and-quality` for Review.
- **Pause:** none, unless the message asks for one. The unit of a pause in this repo is <one plan | one package>. A run ends at its pause: the last message says what is done and names the next part, and it holds no question.
- **Subagents:** at most <n> at the same time.
- **Choices:** make each judgment call yourself. Take the option you would recommend, and write it in the decision log, with the reason. The decision log is the file that the message names, and `tasks/decisions.md` when it names none.
- **What waits for the user:** the message lists it. Do not do such a step, and do not wait for it. Write what it waits for in the decision log, and go on with the tasks that do not depend on it. Only a branch that holds such a step is not merged.
- **Merge:** the Build section decides. Merge only when the user's own message says that merging without their approval is fine, the verify command passed on the branch, a fresh subagent reviewed it and you fixed the findings. The main session merges: a subagent never does. In a repo with no remote, open no pull request: the subagent reviews the branch against the default branch, and the main session merges it with `git merge --no-ff` and pushes nothing.
- **CI:** <this repo runs no CI on a pull request, so wait for none: the verify command is the gate | CI runs on each pull request: wait for the run before a merge, fix a failed run, and when a run cannot start, record that and go on with the verify command>
- **Programs with a window:** <none | the programs that a check may start without asking, such as a game client>

## Reports

Report every guess and every gap you accepted. Put any choice that changes user-visible behavior to the user before you commit.
