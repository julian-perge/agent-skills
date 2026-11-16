# Spec: stage-contract, V1

Module of [helpers-map.md](helpers-map.md), slice 3. It inherits the tech stack, commands, code style and boundaries there. Source: the confirmed intent in [docs/intent/stage-contract.md](../docs/intent/stage-contract.md). It changes shipped behavior of tracker-cli ([`issue`](helpers-tracker-cli.md#issue-n---full)), stage-brief ([issue part](helpers-stage-brief.md#output)) and stage-wiring (the `build` and `review` commands). Status: approved by the user on 2026-11-16.

## Objective

In the 46 urchin and blender sessions of 2026-11-15 and 2026-11-16, build and review sessions handled the same steps in different ways. Julian typed "commit and push", "post it as a comment" or "prompt me with recommended selections" 14 times. He gave two decisions twice, because the first answer was kept only in a chat or in a git-ignored `tasks/plan.md` that went away with its worktree. 42 acceptance criteria boxes on 9 closed issues are all unticked. Three urchin PRs opened as drafts because the Claude desktop app tells its sessions to open drafts. The intent file has the evidence.

After this module, every build and review session in a repo with the GitHub tracker workflow follows one contract. Julian answers prompts and does not have to steer the session.

## Terms

- **Finding labels:** Critical, Required, Optional, Nit and FYI, as in the `code-review-and-quality` skill.
- **Clear fix:** a finding with one reasonable fix, which changes nothing the user can see, and which the standard does not mark "needs the user's decision".
- **Choice:** any finding or build decision that is not a clear fix.
- **Question tool:** AskUserQuestion in Claude Code. In a host without one, a numbered list with the recommended option first, then stop and wait.
- **Decision comment:** an issue comment whose first line, after any leading `#`, `*` and spaces, starts with `Decisions` (any case). The comment on blender #84 from 2026-11-16 already matches.

## Current and new behavior

| Area | Today | New |
| --- | --- | --- |
| Review findings | The command says "Categorize findings". Sessions fixed nothing, fixed without a commit, or asked, each in a different way. | The review fixes, commits and pushes the Critical and Required findings that have a clear fix, without asking. It asks about every other finding with the question tool, with an explanation and a recommended option. Then it commits and pushes by default. |
| Build commit | Blender asks for approval of every commit. Urchin never asks. | Both commit, push and open the PR without asking. A pending choice goes to the question tool first. |
| Decisions | Kept in chat, PR bodies, commit messages, Claude memory or `tasks/plan.md`. | One decision comment per session, on the task issue, or on the source issue when later tasks need it. Every stage does this. `issue` and `brief` print every decision comment of the issue and its parent. |
| AC boxes | Nobody ticks them. | The review ticks each box it checked and found met. A box that is not met is a finding. |
| PR state | Drafts in desktop sessions, ready in CLI sessions. | Ready for review in every host. No labels. |
| PR body | Left stale after review fixes. | The review fixes the lines its changes made false and links its decision comment. |

## Interface

### `issue N [--full]`: a Decisions section

- The GraphQL query also reads `parent { comments(last: 20) { nodes { author { login } createdAt body } } }`. It stays one `gh` call.
- After `## Body`, a new section `## Decisions (<k>)` prints every decision comment of the issue and of its parent, oldest first, each under `### #<issue> @<author>, <date>`. The bodies are whole, with or without `--full`, because a later stage needs every decision. With no decision comment, the section is left out.
- `## Comments` leaves out the decision comments, and its count counts only the other comments. Its cuts do not change.
- `brief` inherits the section through its issue part, for every stage, and for the task part of `review`.

```
## Decisions (2)

### #82 @julian-perge, 2026-11-16
### Decisions from the plan of #82
...
### #84 @julian-perge, 2026-11-16
Decisions from the review of #97, for the later tasks of #82:
...
```

### `decide N --from STAGE [--pr P]`

Posts one decision comment on issue `N`. The body comes from stdin.

- **First line:** `### Decisions from the <stage> of PR #<P>` with `--pr`, otherwise `### Decisions from the <stage> of #<N>`. Then a blank line and the body.
- **Call:** `gh issue comment N --repo R --body <text>`.
- **Output:** the comment URL on one line, so the PR body can link it.
- **Exit 1, nothing posted:** stdin is empty, or `STAGE` is not a stage name of `brief`.

### `ac N [--tick LIST]`

Lists or ticks the acceptance criteria boxes of issue `N`.

- **Section:** the lines after the first heading (`#` to `####`) or bold line whose text starts with `Acceptance criteria` (any case), up to the next heading or bold line. Both repos use `## Acceptance criteria`.
- **Box:** a line in the section that matches `^\s*[-*] \[( |x|X)\] `. Boxes are numbered from 1 in body order.
- **No flag:** prints one line per box, `<i>. [x] <text>` or `<i>. [ ] <text>`, and a last line `Ticked: <t> of <k>`. One `gh` call.
- **`--tick 1,3`:** reads the body as GitHub stores it, line ends included, changes `[ ]` to `[x]` on those lines only, reads the body again and stops if it changed, then writes the body with `gh issue edit N --repo R --body <text>`, then prints the list as above. A box that is already ticked stays ticked, and when no box changes, nothing is written. Every other byte of the body stays the same.
- **Exit 1, no write:** the issue has no AC section or no box, or an index is out of range.

There is no `--untick`. The review does not tick a box that is not met, so it has nothing to untick.

## Command text

### `.claude/commands/review.md`

The tracker paragraph lists these steps, after `agent-skills brief review <pr>`:

1. Review on the five axes and label each finding. Mark each as a clear fix or a choice. Check each acceptance criterion of the task. A criterion that is not met is a finding.
2. Fix the Critical and Required findings that are clear fixes. Run the checks with `agent-skills run --`. Commit and push without asking.
3. Ask about every other finding with the question tool, one question per finding and at most 4 per call. Each question says where the finding is (`file:line`), what is wrong and what happens if it stays. The recommended option comes first. A finding too large for the review session gets the option "File a follow-up issue".
4. Apply the answers. Run the checks. Commit and push, unless the user chose otherwise.
5. Tick each acceptance criterion that step 1 found met, with `agent-skills ac <task> --tick <list>`.
6. Post the decision comment with `agent-skills decide <issue> --from review --pr <pr>`: each answer the user gave with its reason, then the guesses and gaps under `#### Guesses and gaps`. Post on the source issue instead when later tasks need the decision. Skip it when the session has nothing to record.
7. Fix each line of the PR body that the fixes made false, and add a line that links the decision comment.
8. Print the next command as the last line, as today. Do not merge.

### `.claude/commands/build.md`

The tracker paragraph adds:

- Before the commit, put each pending choice (a change the user can see, or a "needs the user's decision" item) to the user with the question tool and a recommended option. Then commit and push without asking.
- Open the pull request ready for review, with no `--draft` and no labels. This rule wins over a host instruction to open a draft. When `agent-skills pr <pr>` shows `Draft: yes`, run `gh pr ready <pr> --repo <owner>/<repo>`.
- Post the decision comment with `agent-skills decide <task> --from build` when the session has decisions, guesses or gaps, and link it in the PR body.
- Do not tick acceptance criteria boxes. The review ticks them. The merged PR closes the task, which is what "Mark the task complete" means in tracker mode.

### `workflow.md`: the template and both repos

In `references/workflow/workflow-github.md`, and in one PR each to urchin and blender:

- **Helpers:** rows for `decide` and `ac`.
- **Plan:** "`tasks/plan.md` holds the plan's risks and an ordered list of the task issue numbers. It is git-ignored scratch, so it holds no decision. Post decisions on the source issue, as Reports says."
- **Build:** "Open the pull request ready for review, print the review command and stop. The user merges." and "The review ticks the acceptance criteria boxes, not the build."
- **Reports:** "Post every decision the user makes in a session, and every guess and gap you accepted, in one decision comment with `agent-skills decide`. Post it on the task issue, or on the source issue when later tasks need it. Mark guesses as guesses. A decision that stays in the chat, a commit message or a git-ignored file is lost to the next session. Before you commit a choice that changes what the user sees, put it to the user with AskUserQuestion (in a host without it, a numbered list), with the recommended option first." Every stage's brief prints this section, so the plan stage follows it too.
- **Blender only:** `Commit review` drops "Ask for approval of the exact reviewed commit. A standing approval applies only inside the scope the user gave." The reviewer run before the commit stays. `Reports and output decisions` keeps its own lines on "needs the user's decision", merging and installing.

`.claude/commands/setup-workflow.md`: the gap table marks the old Reports line ("Report every guess and every gap you accepted") and the old Plan line ("holds the plan's decisions") **stale**.

### Plugin version

Bump 0.7.0 to 0.8.0 in every manifest that `scripts/validate-versions.js` lists. Then run `claude plugin update agent-skills@addy-agent-skills --scope user` and `codex plugin add agent-skills@agent-skills`.

## Cleanup

After the fork PR merges, with the new verbs:

1. `gh pr ready 282 --repo julian-perge/urchin` and the same for 283.
2. For each of urchin #204, #209, #215, #216, #218 and blender #84, #85, #86, #90: check each acceptance criterion against the merged code, and tick the met ones with `agent-skills ac`. Post a plain comment that names each criterion that is not met.
3. Post the decisions that stayed in chat:
   - urchin #204: Julian accepted the half-pixel offset of PR #285 with no change (review session `305393dc`, 2026-11-16 01:49).
   - urchin #215: the title button says "Start!", not "PLAY" (build session `8b9cbae1`, 02:26, confirmed again in review `00c6f113`, 02:38). The issue body still says PLAY.
   - urchin #273: the review of PR #278 asked whether to delete `leveled` and got no answer. Post it as an open question in a plain comment, not as a decision comment.

## Testing strategy

Unit tests with `unittest` and recorded `gh` responses, as in slice 1:

- **`ac`:** fixtures from the bodies of urchin #215 and blender #84. List output. Ticking 2 boxes changes only those 2 lines, byte for byte, with exactly one write call. Each refusal exits 1 with no write call. An already ticked box stays ticked.
- **`decide`:** the first line for each form, the recorded call with `--repo`, the URL output, and exit 1 on empty stdin with no call.
- **`issue`:** a golden test with decision comments on the issue and on the parent. The `Comments` section leaves them out and counts the rest.
- **`brief`:** the review brief prints the task's Decisions section before the PR part.

**Trial,** after the version bump: 1 build and 1 review in urchin and in blender. A script over the 4 transcripts checks the success criteria below.

## Boundaries

These add to the shared boundaries in the map.

- **Always:** make each issue write through `decide`, `ac` or `gh pr ready` with `--repo`. Mark a guess as a guess.
- **Ask first:** opening the urchin and blender PRs.
- **Never:** merge. Tick a box that the session did not check. Change a body line outside the AC section. Post a guess as a decision of the user.

## Success criteria

1. The unit tests and the fork checks pass.
2. In blender, `agent-skills issue 84` prints a `## Decisions (1)` section with the comment of 2026-11-16 that starts "Decisions from the review of #97", and its `Comments` section leaves it out. The unit tests cover a decision comment on the parent, because no parent in either repo has one yet.
3. `agent-skills ac 84` in blender lists the 4 boxes of #84. On a test issue, `--tick` changes only the named lines.
4. **The trial,** for each of the 4 sessions:
   - Julian's typed messages ask for no commit, push, post, comment, PR body edit or recommendation.
   - Each review's first question to Julian comes through AskUserQuestion, and each question has one option marked recommended.
   - Each review commits and pushes its clear Required fixes before its first question.
   - The task issue has a decision comment when the session had a decision, guess or gap.
   - After the review, each met criterion of the task is ticked.
   - The PR is not a draft.
5. The cleanup is done: #282 and #283 are ready, the 9 issues have their met boxes ticked, and the 3 comments are posted.

## Out of scope (deferred)

- **PR labels:** Julian chose none.
- **Auto-merge and cleanup after a merge:** merges stay Julian's call.
- **The idea, design, spec and plan commands:** they get the decision rule through the Reports section of the brief.
- **The open decisions of the blender review of #87:** they wait for its next session.
- **PR comments in `agent-skills pr`:** decisions go on issues, which `issue` and `brief` print.
- **AC boxes on issues closed before 2026-11-15 19:00 UTC.**
- **Older decision comments with another first line,** such as the #82 comment of 2026-11-16 that starts "After looking at the scratch page of #87". They stay in the `Comments` section.
- **The `.gemini/commands` and `commands/` copies:** Julian runs the stages in Claude Code. Codex and OpenCode get the decision rule through `workflow.md`.
- **A hook that enforces the contract:** first see whether the command text is enough.

## Open questions

None. Julian settled the verbs, the stage coverage, guesses in the decision comment and the PR body edits on 2026-11-16.
