# Implementation Plan: agent-skills helpers, slice 3 (stage-contract)

Source spec: spec/helpers-stage-contract.md (map: spec/helpers-map.md). Status: approved by the user on 2026-11-16.

Tasks are in [tasks/todo.md](todo.md). The task list below is an ordered index only, so the two files cannot drift apart. The plans of slices 1 and 2 are in `tasks/done/`.

## Overview

Slice 3 gives build and review one contract in every repo with the GitHub tracker workflow. The helpers get two write verbs, `decide` and `ac`, and `issue` gets a Decisions section that `brief` passes on. The `build` and `review` commands and the workflow seed get the contract text. Then urchin and blender take the new `workflow.md` text, the cleanup runs, and a trial of 4 sessions checks the result.

## Architecture decisions

- **A decision comment is found by its first line.** `tracker.is_decision(body)` strips leading `#`, `*` and spaces and checks for `Decisions`, in any case. It is a pure function, so `issue`, `decide` and the tests share one rule.
- **The parent's comments come in the same query.** `ISSUE_QUERY` reads `parent { ... comments(last: 20) ... }`, so `issue` stays one `gh` call. `parse_issue` reads the field with a default, so the slice 1 and 2 fixtures that do not have it still parse.
- **The AC rules are pure functions in `tracker.py`:** find the section, number the boxes, tick a list of them. `github.py` only reads the body and writes it back, with `gh issue edit N --repo R --body <text>`.
- **`ac --tick` reads the body again just before it writes.** If the body changed since the first read, it stops with exit 1 and writes nothing, so a concurrent edit is not lost.
- **`decide` writes the first line itself.** The command text describes the body (the user's answers, then `#### Guesses and gaps`), and the verb does not check it.
- **The live check of `--tick` uses the first cleanup issue, not a test issue.** The fork has no test issue, and the cleanup ticks real boxes anyway. The body is saved before and compared after, and the diff must show only the ticked lines. (A deviation from spec criterion 3's "test issue". Say so if you want a scratch issue instead.)
- **The plugin reinstall runs after the fork PR merges.** Both hosts copy the checkout, so the copy must come from `main`.
- **`.gemini/commands/` and `commands/` stay as they are,** as the spec says.

## Task list (index)

Phase 1, the helpers: 1, 2, 3, checkpoint A.
Phase 2, the fork's text: 4, 5, 6, checkpoint B.
Phase 3, other repos, cleanup and the trial: 7, 8, checkpoint C, 9, checkpoint D.

Task 1 comes first because it changes the shared `issue` query and its fixtures, which tasks 2 and 3 build on.

## Parallel work

- Tasks 1, 2 and 3 all touch `cli.py`, `github.py` and `tracker.py`, so they run in order.
- Tasks 4 and 5 touch different files and need only the verb names, so they can run beside phase 1.
- Tasks 7 and 8 need the fork PR merged. They touch different repos and files, so they can run side by side.
- Task 9 needs task 7 merged and the 0.8.0 install.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| A host instruction to open a draft PR wins over the command text | Med | The build text says it wins and adds a `gh pr ready` step. The trial checks the PR state. A hook stays deferred. |
| Codex and OpenCode have no AskUserQuestion | Med | The question tool term names a numbered list with the recommended option first as the fallback. Codex and OpenCode do not run the fork's commands today. |
| `--tick` loses an edit that someone else made at the same time | Low | The read just before the write, which stops on a change. |
| An agent reads "Required, clear fix" too widely and commits a choice without asking | Med | The term lists all three tests. The trial checks each commit made before the first question. |
| A trial needs ready tasks in both repos | Low | Task 9 picks them with `agent-skills next` when it starts. |
| Open sessions still run 0.7.0 | Low | Task 7 restarts nothing. Task 9 starts new sessions only. |

## Open questions

- The live check of `--tick` (see the architecture decisions).
