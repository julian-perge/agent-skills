# Tasks: agent-skills helpers, slice 3 (stage-contract)

Source spec: spec/helpers-stage-contract.md. Plan: [tasks/plan.md](plan.md).

Shared commands (from the map):

```
Unit tests:   PYTHONPATH=scripts python3 -m unittest discover -s scripts/agent_skills/tests
Fork checks:  node scripts/validate-skills.js && node scripts/validate-commands.js && node scripts/validate-reference-links.js && node scripts/validate-artifact-paths.js && node scripts/run-evals.js --min-rank1 95
Plugin check: claude plugin validate .
```

## Phase 1: the helpers

- [x] **Task 1: `issue` prints the decision comments of the issue and its parent**
  - Description: Add `tracker.is_decision`, the parent's comments in `ISSUE_QUERY` and `parse_issue`, and a `## Decisions (<k>)` section in `render.issue_report`, after `## Body`. `## Comments` leaves the decision comments out and counts the rest. `brief` passes the section on with no change of its own.
  - Acceptance:
    - A golden test from a trimmed real response of blender #84, with one decision comment added to its parent #82, prints both decision comments whole, oldest first, under `### #<issue> @<author>, <date>`. The `Comments` heading counts only the other comments.
    - With no decision comment, the output of the existing `issue` and `brief` fixtures does not change, byte for byte.
    - `is_decision` is true for `### Decisions from ...`, `**Decisions**` and `decisions:`, and false for "The decisions below" and an empty body.
    - The review brief prints the task's Decisions section before the PR part.
  - Verify: the unit tests, then `agent-skills issue 84` in blender (spec criterion 2).
  - Dependencies: none.
  - Files: `scripts/agent_skills/tracker.py`, `scripts/agent_skills/github.py`, `scripts/agent_skills/render.py`, `scripts/agent_skills/tests/test_issue.py`, `scripts/agent_skills/tests/test_brief.py`, with new fixtures `issue-blender-84.json` and `issue-blender-84.md`.
  - Scope: M.

- [x] **Task 2: The `ac` verb**
  - Description: Add `ac N [--tick LIST]`. Pure functions in `tracker.py` find the AC section, number its boxes and tick a list of them. `github.py` reads the body and writes it with `gh issue edit N --repo R --body <text>`, after a second read that must equal the first.
  - Acceptance:
    - The list form prints `<i>. [ ] <text>` or `<i>. [x] <text>` for each box, then `Ticked: <t> of <k>`, from one `gh` call.
    - Ticking 2 boxes of the urchin #215 fixture changes only those 2 lines, byte for byte, and records exactly one write call. A ticked box stays ticked.
    - No AC section, no box, an index out of range, or a body that changed between the two reads: exit 1 with the reason, and no write call.
  - Verify: the unit tests, then `agent-skills ac 84` in blender lists 4 boxes.
  - Dependencies: 1 (the shared files).
  - Files: `scripts/agent_skills/tracker.py`, `scripts/agent_skills/github.py`, `scripts/agent_skills/cli.py`, `scripts/agent_skills/tests/test_ac.py`, with new fixtures from the bodies of urchin #215 and blender #84.
  - Scope: M.

- [x] **Task 3: The `decide` verb**
  - Description: Add `decide N --from STAGE [--pr P]`. It reads the body from stdin, writes the first line `### Decisions from the <stage> of #<N>` (or `of PR #<P>`), posts with `gh issue comment N --repo R --body <text>` and prints the URL that `gh` returns.
  - Acceptance:
    - Both first-line forms, and `is_decision` is true for each.
    - The recorded call has `--repo` and the body on stdin. The output is the URL alone.
    - Empty stdin, or a stage that `brief` does not know: exit 1, and no call.
  - Verify: the unit tests.
  - Dependencies: 1.
  - Files: `scripts/agent_skills/cli.py`, `scripts/agent_skills/github.py`, `scripts/agent_skills/tests/test_decide.py`.
  - Scope: S.

### Checkpoint A: the helpers work

- [ ] The unit tests pass locally and in CI on the pushed branch.
- [x] Spec criterion 2 holds, and `agent-skills ac 84` lists the 4 boxes of #84.
- [ ] The user looks at the `agent-skills issue 84` output.

## Phase 2: the fork's text

- [ ] **Task 4: The review and build contract**
  - Description: Write the spec's 8 review steps into the tracker paragraph of `.claude/commands/review.md`, and the 4 build rules into `.claude/commands/build.md`, with the spec's terms (clear fix, choice, question tool).
  - Acceptance:
    - Each step and rule of the spec's "Command text" section is in the file, in the spec's order.
    - The upstream text outside the tracker paragraphs does not change.
  - Verify: the fork checks, and the user reads the two diffs.
  - Dependencies: the verb names of tasks 2 and 3 only.
  - Files: `.claude/commands/review.md`, `.claude/commands/build.md`.
  - Scope: S.

- [ ] **Task 5: The workflow seed and the setup template**
  - Description: In `references/workflow/workflow-github.md`, add the `decide` and `ac` Helpers rows and the new Plan, Build and Reports text from the spec. In `.claude/commands/setup-workflow.md`, mark the old Reports and Plan lines **stale** in the gap table.
  - Acceptance:
    - The seed's text equals the spec's quotes.
    - `agent-skills brief build` run on the seed prints the new Reports section.
  - Verify: the fork checks, and the `brief` tests still pass.
  - Dependencies: the verb names only.
  - Files: `references/workflow/workflow-github.md`, `.claude/commands/setup-workflow.md`.
  - Scope: S.

- [ ] **Task 6: Version 0.8.0 and the fork PR**
  - Description: Bump 0.7.0 to 0.8.0 in every manifest that `scripts/validate-versions.js` lists. Open the fork PR with `--repo julian-perge/agent-skills`.
  - Acceptance:
    - `node scripts/validate-versions.js` passes.
    - The PR is open, ready for review, and its CI passes.
  - Verify: the fork checks, the plugin check and the PR's checks.
  - Dependencies: 1 to 5.
  - Files: `plugin.json`, `.codex-plugin/plugin.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`.
  - Scope: XS.

### Checkpoint B: the fork is done

- [ ] Spec criteria 1 and 2 hold, and the list form of criterion 3. Its `--tick` part is checked live in task 8.
- [ ] The user merges the fork PR.
- [ ] `claude plugin update agent-skills@addy-agent-skills --scope user` and `codex plugin add agent-skills@agent-skills` install 0.8.0, and the installed `review.md` has the new steps.
- [ ] The user approves opening the urchin and blender PRs.

## Phase 3: other repos, cleanup and the trial

- [ ] **Task 7: urchin and blender take the new workflow text**
  - Description: One PR per repo. `docs/agents/workflow.md` gets the Helpers rows and the Plan, Build and Reports text of task 5. Blender's `Commit review` drops its two approval sentences, and its `Reports and output decisions` keeps its own lines.
  - Acceptance:
    - `agent-skills brief build <n>` in each repo prints the new Reports text.
    - In blender, the brief no longer says "Ask for approval of the exact reviewed commit".
  - Verify: the brief output in each repo, and each PR's checks.
  - Dependencies: checkpoint B.
  - Files: `docs/agents/workflow.md` in urchin and in blender.
  - Scope: S.

- [ ] **Task 8: The cleanup**
  - Description: Do the spec's Cleanup section with the new verbs. Before the first `--tick`, save that issue's body, and compare it after.
  - Acceptance:
    - urchin #282 and #283 are ready for review.
    - Each of the 9 issues has its met boxes ticked, and a plain comment names each box that is not met, with the reason.
    - The #204 and #215 decision comments and the #273 open-question comment are posted.
    - The first ticked body differs from the saved body only on the ticked lines (spec criterion 3, live).
  - Verify: `agent-skills ac <n>` for each of the 9 issues, and `agent-skills issue 204` and `agent-skills issue 215` print a Decisions section.
  - Dependencies: checkpoint B.
  - Files: none in a repo. GitHub writes only.
  - Scope: M.

### Checkpoint C: before the trial

- [ ] The urchin and blender PRs are merged.
- [ ] Spec criterion 5 holds.

- [ ] **Task 9: The trial**
  - Description: The user runs 1 build and then its review in urchin, and the same in blender, in new sessions on 0.8.0. A script reads the 4 transcripts and checks spec criterion 4. Write the results into `docs/ideas/agent-skills-helpers.md`, as slices 1 and 2 did.
  - Acceptance: each point of spec criterion 4 holds for each session, or the user accepts the miss.
  - Verify: the script's output, and the issue and PR state in `gh`.
  - Dependencies: checkpoint C.
  - Files: `docs/ideas/agent-skills-helpers.md`, and the script in `~/tmp/2026-11-16-session-audit/`.
  - Scope: M.

### Checkpoint D: slice 3 complete

- [ ] Every success criterion in `spec/helpers-stage-contract.md` holds, or the user accepts the miss.
- [ ] The spec's status says implemented, and the map says slice 3 is done.
