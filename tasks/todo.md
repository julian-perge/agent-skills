# Tasks: agent-skills helpers, slice 2 (stage-brief)

Source spec: spec/helpers-stage-brief.md. Plan: [tasks/plan.md](plan.md).

Shared commands (from the map):

```
Unit tests:   PYTHONPATH=scripts python3 -m unittest discover -s scripts/agent_skills/tests
Fork checks:  node scripts/validate-skills.js && node scripts/validate-commands.js && node scripts/validate-reference-links.js && node scripts/validate-artifact-paths.js && node scripts/run-evals.js --min-rank1 95
Plugin check: claude plugin validate .
```

## Phase 1: the verb

- [x] **Task 1: Split workflow.md into the sections of one stage**
  - Description: Add `scripts/agent_skills/brief.py` with the stage table and a pure function that returns the sections of one stage in file order, as the spec's section map says.
  - Acceptance:
    - For each of the seven stages, the fixture gives the headings that the map names, in file order, with each section's text byte for byte.
    - A heading that the map does not know appears in every stage. A known heading that is missing is skipped.
    - The command names `idea-refine`, `interview-me` and `test` give the same result as `idea`, `design` and `bug`.
  - Verify: the unit tests. Fixtures: blender's and urchin's `docs/agents/workflow.md` from `origin/main` on 2026-11-15.
  - Dependencies: none.
  - Files: `scripts/agent_skills/brief.py`, `scripts/agent_skills/tests/test_brief.py`, `scripts/agent_skills/tests/fixtures/workflow-blender.md`, `scripts/agent_skills/tests/fixtures/workflow-urchin.md`.
  - Scope: S.

- [x] **Task 2: The `brief` verb**
  - Description: Add `brief <stage> [<n>] [--full]` to `cli.py`. It reads `docs/agents/workflow.md` at the checkout root, prints the rules from task 1, then the output of `issue_verb` or `pr_verb` from its second line under a new heading.
  - Acceptance:
    - `review` uses `pr`. Every other stage uses `issue`. A leading `#` on the number is accepted.
    - With no number, the verb prints the rules only and records no `gh` call.
    - A repo with no `workflow.md` gives exit 2 and names `/agent-skills:setup-workflow`.
    - The recorded `gh` calls equal those of `issue` or `pr` for the same number.
  - Verify: the unit tests, then spec criteria 2 to 4 by hand in blender (`agent-skills brief build 74`, `agent-skills brief review 79`, `agent-skills brief build`).
  - Change at checkpoint A (2026-11-15): the user asked for one rules heading, no first intro paragraph, no `Earlier layout`, the whole issue body and one comment. The spec has the new output.
  - Dependencies: 1.
  - Files: `scripts/agent_skills/cli.py`, `scripts/agent_skills/tests/test_brief.py`.
  - Scope: S.

### Checkpoint A: the verb works

- [x] The unit tests pass locally and in CI on the pushed branch.
- [x] Spec criteria 2 to 4 hold in blender.
- [x] The user looks at the `brief build 74` output before the stage files name the verb.

## Phase 2: the fork's text

- [x] **Task 3: The stage commands start with `brief`**
  - Description: In `build.md`, `review.md`, `plan.md` and `spec.md`, replace the first `agent-skills issue <n>` or `agent-skills pr <pr>` with `agent-skills brief <stage> <n>`. Add the same line to `test.md`. Each line says to read the whole output, with no `head` or `tail`, and to add `--full` for the whole issue body.
  - Acceptance:
    - Each of the five files names `agent-skills brief` with its own stage.
    - No other line of those files changes.
  - Verify: the fork checks, the plugin check, and `codex plugin add agent-skills@agent-skills`.
  - Dependencies: 2.
  - Files: `.claude/commands/build.md`, `review.md`, `plan.md`, `spec.md`, `test.md`.
  - Scope: S.

- [ ] **Task 4: The seed and the setup template name `brief`**
  - Description: Change the intro of `references/workflow/workflow-github.md` and add a `brief` row to its Helpers table. Change the `## Workflow` block in `setup-workflow.md` to the new line from the spec, and mark the old line **stale** in the gap table.
  - Acceptance:
    - The seed's intro says that `agent-skills brief` prints the parts a stage needs, and the Helpers table has the `brief` row.
    - The setup template's block has the line "Start each `/agent-skills` stage with `agent-skills brief <stage> <n>`. Read all of `docs/agents/workflow.md` before other work in this repo."
    - The gap table names the old line "Read `docs/agents/workflow.md` before any `/agent-skills` command." as stale.
  - Verify: the fork checks.
  - Dependencies: 2.
  - Files: `references/workflow/workflow-github.md`, `.claude/commands/setup-workflow.md`.
  - Scope: S.

### Checkpoint B: the fork is done

- [ ] Spec criterion 1 holds.
- [ ] The user approves opening the urchin and blender PRs.

## Phase 3: other repos and the trial

- [ ] **Task 5: urchin and blender start each stage with `brief`**
  - Description: Open one PR in each repo. Each changes the `## Workflow` line of `AGENTS.md` to the setup template's new line, and changes the intro and the Helpers table of `docs/agents/workflow.md` to the seed's. Owner text stays.
  - Acceptance:
    - Each `AGENTS.md` names `agent-skills brief` and no longer says to read `workflow.md` before any command.
    - Each `workflow.md` has the `brief` row, and its other sections are unchanged.
    - Each change is in a PR, and the user merges it.
  - Verify: the PR diff in each repo.
  - Dependencies: 3, 4, checkpoint B.
  - Files: urchin and blender `AGENTS.md` and `docs/agents/workflow.md`.
  - Scope: S.

### Checkpoint C: before the trial

- [ ] Spec criterion 5 holds.

- [ ] **Task 6: Run the trial again**
  - Description: Count a read of a `spec/` file as a source read in `~/tmp/2026-11-15-agent-cli-audit/targets.py`, and count calls that read all of `docs/agents/workflow.md`. After the user runs 3 build sessions and 2 review sessions in blender, run `targets.py` over them and write the numbers into the idea doc.
  - Acceptance:
    - At most 1 Bash call before the first read of `src/`, `tests/` or `spec/`, or a `git diff`.
    - 0 calls that read all of `docs/agents/workflow.md`.
    - 0 raw `gh issue view` calls, and 0 tail-only test reruns.
    - A miss is recorded with its numbers, not hidden.
  - Verify: the numbers and the session ids are in `docs/ideas/agent-skills-helpers.md`.
  - Dependencies: 5.
  - Files: `docs/ideas/agent-skills-helpers.md`. Outside the repo: `targets.py`.
  - Scope: XS.

### Checkpoint D: slice 2 complete

- [ ] Every success criterion in `spec/helpers-stage-brief.md` holds, or the user accepts the miss.
