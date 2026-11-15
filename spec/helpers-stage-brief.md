# Spec: stage-brief, V1

Module of [helpers-map.md](helpers-map.md), slice 2. It inherits the tech stack, commands, code style and boundaries there. Status: approved by the user on 2026-11-15. The user changed the output at checkpoint A on 2026-11-15: one rules heading, no first intro paragraph, no `Earlier layout`, the whole issue body and one comment.

## Objective

In the slice 1 trial, every stage session used 2 to 4 Bash calls before it read any source ([trial results](../docs/ideas/agent-skills-helpers.md#trial-results-slice-1-2026-11-15)). The first call was always `cat docs/agents/workflow.md`, because the agent file says to read it before any `/agent-skills` command. The second call was `agent-skills issue <n>` or `agent-skills pr <pr>`. In blender, `workflow.md` has 8,798 characters, and a stage needs about half of them.

`agent-skills brief <stage> [<n>]` prints the parts of `workflow.md` that the stage needs, then the issue or PR brief, in one call. The users are the agents that run the stages in Claude Code, Codex and the OpenCode workers.

## Interface

```
agent-skills [--repo OWNER/REPO] brief <stage> [<n>] [--full]
```

- **Stage:** one of `idea`, `design`, `spec`, `plan`, `build`, `bug`, `review`. The command names `idea-refine`, `interview-me` and `test` are accepted too, for `idea`, `design` and `bug`.
- **Number:** an issue number, or a PR number for `review`. A leading `#` is accepted. With no number, the verb prints the rules only. `/agent-skills:build auto` uses that form.
- **`--full`:** passed to `issue` or `pr`.
- **Exit codes:** as the other verbs. A missing `docs/agents/workflow.md` at the repo root gives exit 2 and a message that names `/agent-skills:setup-workflow`.

### Output

```
# Rules for build, from docs/agents/workflow.md

<the intro, without its title line and its first paragraph>
## Helpers
...
## Build
...
## Commit review
...
# Issue #74
<the output of agent-skills issue 74, from its second line, with the whole body and one comment>
```

The sections keep their order in the file and their text byte for byte. The intro loses only its `# ` title line and its first paragraph, which tells the agent to read the whole file. An intro with nothing left is skipped.

The issue part prints the whole body, because a build needs its acceptance criteria and verification, and only the newest comment, cut at 600 characters. With `--full`, it equals `agent-skills issue <n> --full`. For `review`, the last part is the output of `agent-skills pr <n>`, with its own cuts. The `gh` calls are the calls of `issue` or `pr`, and `brief` adds none.

### Section map

A section is a `## ` heading and the lines up to the next `## ` heading. Headings match without case and by the first word, so `## Reports and output decisions` is `Reports`.

| Heading | Stages |
| --- | --- |
| The text before the first heading, `Helpers`, `Reports` | every stage |
| `Stages` | idea, design |
| `Design` | idea, design, spec |
| `Spec` | spec |
| `Plan`, `Labels` | plan |
| `Build` | build, bug |
| `Review` | review |
| `Earlier`, such as blender's `Earlier layout` (old spec and task paths) | no stage |
| Any other heading, such as blender's `Commit review` | every stage |

An unknown heading goes to every stage, so owner text is never dropped. A known heading that is missing from the file is skipped with no note.

## Changes

In the fork:

1. `scripts/agent_skills/brief.py` and the `brief` verb in `cli.py`, with tests in `scripts/agent_skills/tests/test_brief.py`. The tests use a copy of blender's `workflow.md` as a fixture.
2. `.claude/commands/build.md`, `review.md`, `plan.md`, `spec.md` and `test.md`: start with `agent-skills brief <stage> <n>` in place of `agent-skills issue <n>` or `agent-skills pr <pr>`. Each says to read the whole output, with no `head` or `tail`. The `.gemini` and `commands/` bodies change their pointer text only.
3. `references/workflow/workflow-github.md`: the intro says that `agent-skills brief` prints the parts a stage needs. The Helpers table gets a `brief` row.
4. `.claude/commands/setup-workflow.md`: the agent file's `## Workflow` block says "Start each `/agent-skills` stage with `agent-skills brief <stage> <n>`. Read all of `docs/agents/workflow.md` before other work in this repo." in place of "Read `docs/agents/workflow.md` before any `/agent-skills` command." The gap table marks the old line **stale**.
5. `~/tmp/2026-11-15-agent-cli-audit/targets.py`: a read of a `spec/` file counts as a source read.

In urchin and in blender, one PR each, after the user approves: the same `## Workflow` line in `AGENTS.md`, and the intro and the Helpers row in `docs/agents/workflow.md`.

## Testing strategy

Unit tests with `unittest` and the recorded `gh` responses of slice 1. For each stage, a test checks which headings of the fixture appear and in which order. One test adds an unknown heading and checks that every stage prints it. One test checks the issue part against the `issue` output, its whole body and its one comment, and one that `review` uses `pr`. One test checks that the intro loses its title and first paragraph. One test checks the exit 2 for a repo with no `workflow.md`.

## Boundaries

These add to the shared boundaries in the map.

- **Always:** keep the text of each section byte for byte.
- **Ask first:** opening the urchin and blender PRs.
- **Never:** rewrite or reorder the text of a repo's `workflow.md` to fit the map.

## Success criteria

1. The unit tests and the fork checks pass.
2. In blender, `agent-skills brief build 74` prints one `# ` heading for the rules, the intro without its first paragraph, `Helpers`, `Build`, `Commit review` and `Reports and output decisions`, in file order, and no `Earlier layout`. Then it prints the `agent-skills issue 74` output after its first line, with the whole body and only the newest comment.
3. `agent-skills brief review 79` in blender ends with the same two lines as `agent-skills pr 79`.
4. `agent-skills brief build` with no number prints the rules and no brief, and it makes no `gh` call.
5. The urchin and blender PRs are merged, and their `AGENTS.md` line names `agent-skills brief`.
6. **The trial.** Run 3 build sessions and 2 review sessions in urchin. Blender had no task ready to build on 2026-11-15, so the user moved the trial there. The slice 1 numbers are from blender. `targets.py` over them must show:
   - At most 1 Bash call before the first read of `src/`, `tests/` or `spec/`, or a `git diff`.
   - 0 calls that read all of `docs/agents/workflow.md`.
   - 0 raw `gh issue view` calls, and 0 tail-only test reruns.

   Write the numbers into [docs/ideas/agent-skills-helpers.md](../docs/ideas/agent-skills-helpers.md).

## Out of scope (deferred)

- **A `UserPromptSubmit` hook that runs `brief` before the agent starts:** it would make the count 0, but only in Claude Code and Codex. It is also unverified that the hook sees the text of a slash command.
- **The spec file in the brief:** specs can be long. Reading the spec counts as a source read instead.
- **The linked-session note:** the desktop app adds it, not the stage. Some trial sessions read it before any source.
- **Markers in `workflow.md` for each section's stages:** every repo's file would need edits.

## Open questions

None.
