# Implementation Plan: agent-skills helpers, slice 2 (stage-brief)

Source spec: spec/helpers-stage-brief.md (map: spec/helpers-map.md)

Tasks are in [tasks/todo.md](todo.md). The task list below is an ordered index only, so the two files cannot drift apart. Slice 1's plan and tasks are in `tasks/done/slice-1/`.

## Overview

Slice 2 adds one verb, `agent-skills brief <stage> [<n>]`. It prints the `workflow.md` sections that one stage needs, then the issue or PR brief. Then the stage commands, the workflow seed, the setup template, urchin and blender start each stage with it. The last task runs the trial again.

## Architecture decisions

- **The section split is a pure function in `brief.py`.** It takes the text of `workflow.md` and a stage, and returns the sections in file order. It runs no process, so its tests need no fake `gh`.
- **`brief` reuses `issue_verb` and `pr_verb`.** It adds no `gh` call and no second renderer. The brief part is their output from its second line, under a new `# Issue #<n>` or `# PR #<n>` heading.
- **The stage names are a fixed table in `brief.py`.** The command names (`idea-refine`, `interview-me`, `test`) map to the stage names there too.
- **The `.gemini/commands/` and `commands/` stage bodies stay as they are.** None of them names a verb or `workflow.md` today, so the spec's "pointer text only" rule leaves nothing to change.
- **Codex copies the plugin.** After the command edits, `codex plugin add agent-skills@agent-skills` refreshes its copy (slice 1, task 2).

## Task list (index)

Phase 1, the verb: 1, 2, checkpoint A.
Phase 2, the fork's text: 3, 4, checkpoint B.
Phase 3, other repos and the trial: 5, checkpoint C, 6, checkpoint D.

Task 1 comes first because the section map is the one design risk: the heading rules must fit urchin's and blender's files as they are.

## Parallel work

- Task 3 and task 4 touch different files, and both need only the verb name from task 2.
- Task 5 needs tasks 2 to 4, because the repo text names the verb.
- Task 6 needs task 5 merged.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| A repo's `workflow.md` uses a heading that the map reads in the wrong way, such as `## Build and test` | Med | The match is by the first word. Task 1 tests the urchin and blender files as they are on `origin/main`. |
| Agents still read all of `workflow.md`, because the agent file keeps the old line until the repo PRs merge | High | Task 6 starts only after task 5 is merged. |
| Agents still pipe `brief` or `pr` output to `head` | Med | The command files say to read the whole output. The trial counts this. |
| The trial needs 5 new sessions that the user starts | Low | Task 6 says which sessions and gives the commands. |

## Open questions

None.
