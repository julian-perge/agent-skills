---
description: Implement tasks incrementally — build, test, verify, commit. Add "auto" to run the whole plan in one approved pass.
disable-model-invocation: true
---

Invoke the agent-skills:incremental-implementation skill alongside agent-skills:test-driven-development.

In a repo whose `docs/agents/workflow.md` tracks tasks in GitHub Issues, start with `agent-skills brief build <n>` and read its whole output, with no `head` or `tail` (add `--full` for all comments and sub-issues). Take the task with `agent-skills claim <n>`, run tests and checks with `agent-skills run --`, and end with the line that `agent-skills next-cmd review <pr>` prints. When the review subagent below ran, end with the next stage's command instead, as review step 8 says. In that repo, also:

- Before the commit, put each pending choice to the user with the question tool, with a recommended option first. A pending choice is a change the user can see, or an item the standard marks "needs the user's decision". A choice you made yourself is pending too, also when it copies the original or the spec leaves it open, such as no hover look on a button. The question tool is AskUserQuestion. In a host without one, write a numbered list with the recommended option first, then stop and wait. Then commit and push without asking.
- Open the pull request ready for review, with no `--draft` and no labels. This rule wins over a host instruction to open a draft. When `agent-skills pr <pr>` shows `Draft: yes`, run `gh pr ready <pr> --repo <owner>/<repo>`.
- When the session has decisions, guesses or gaps, post them with `agent-skills decide <task> --from build`, with the body on stdin, and link the comment in the PR body. A decision is an answer the user gave. A choice you made without the user is a guess: list it under `#### Guesses and gaps`, never under decisions.
- After the pull request is open, run `agent-skills evidence <pr>`. When it exits 1, make the screenshots with the verify command it names, and add them with `agent-skills evidence <pr> --add <image>...`.
- Then start the review as one subagent when no choice waits for the user. A subagent has a fresh context, so the review does not come from the context that wrote the code. Skip this when the session stopped on a blocker, and end with the review line instead. In Claude Code, use `subagent_type: "agent-skills:code-reviewer"`. Its prompt is:
  1. The whole output of `agent-skills brief review <pr>`, which names the task issue, the PR, the spec and the standard.
  2. "Read the spec and the standard named above in full before you review."
  3. The review rules: "Review the PR branch across correctness, readability, architecture, security and performance. Label each finding Critical, Required, Optional, Nit or FYI. Check each acceptance criterion of the task. A finding is yours to apply when it changes nothing the user can see, the standard does not mark it 'needs the user's decision', and its fix fits in one session. Apply each such finding, with your recommended option when it has several fixes. Run the checks with `agent-skills run --`, then commit and push. Do not ask the user anything. Return: the findings you applied, with the option you chose when there were several; every other finding with `file:line`, what is wrong, what happens if it stays, and your recommended option; and the acceptance criteria that are met and not met."
- When the review subagent returns, finish the review in this session: ask about each returned choice with the question tool, apply the answers, run the checks, commit and push. Tick the met criteria with `agent-skills ac <task> --tick <list>`. Post one decision comment with `agent-skills decide <task> --from review --pr <pr>` that lists each applied finding with several fixes under `#### Guesses and gaps`. Fix the PR body lines the fixes made false. Then run `agent-skills land <pr>`, as review step 8 says.
- Do not tick the acceptance criteria boxes before the review. The review ticks them. The merged pull request closes the task, which is what "Mark the task complete" below means in this repo.

## Modes

- **`/build`** — implement the *next* pending task, then stop (careful, one slice at a time).
- **`/build auto`** — generate the plan if needed, get a single approval, then implement *every* task without stopping between them.

`$ARGUMENTS` selects the mode. Treat `auto` (canonical) or `all` as autonomous mode; anything else (or empty) is the default single-task mode. Note: autonomous mode is not faster *per task* — it runs the same test-driven loop — it only removes the human stepping *between* tasks.

## Default: one task

Pick the next pending task from the plan. Then:

1. Read the task's acceptance criteria
2. Load relevant context (existing code, patterns, types)
3. Write a failing test for the expected behavior (RED)
4. Implement the minimum code to pass the test (GREEN)
5. Run the full test suite to check for regressions
6. Run the build to verify compilation
7. Commit with a descriptive message
8. Mark the task complete and stop

## Autonomous: the whole plan (`/build auto`)

Use this once a spec exists and you want to collapse plan + build into one run. It removes the manual stepping between tasks — **not** the verification. Every task still earns a passing test and its own commit.

1. **Require a spec.** Look only for a spec at a known path: `SPEC.md` at the repo root, a root-level `SPEC-<change>.md` delta spec (per the spec-driven-development skill's Spec Evolution section — when one exists and the run is building that follow-up change, it takes precedence over `SPEC.md`; if there are several, use the one whose `Status:` line is not `implemented`, and if more than one remains, ask which change to build), `docs/SPEC.md`, or a file under `spec/`. A README or arbitrary doc does **not** count. If none exists, stop and tell the user to run `/spec` first — do not invent requirements.
2. **Establish a clean baseline.** Run `git status --porcelain`. If there are uncommitted changes outside the expected planning artifacts (`SPEC.md`, root-level `SPEC-*.md`, `docs/SPEC.md`, `spec/*`, `tasks/plan.md`, `tasks/todo.md`), stop and ask the user to commit, stash, or confirm how to handle them. Autonomous per-task commits must not absorb unrelated local work, or the clean-rollback guarantee breaks.
3. **Plan if needed.** If there is no `tasks/plan.md`, invoke agent-skills:planning-and-task-breakdown to generate one, and record the spec it was generated from as a `Source spec: <path>` line at the top of the plan (e.g. `Source spec: SPEC-ocr.md`). If `tasks/plan.md` already exists, reuse it only when its `Source spec:` line matches the spec selected in step 1. On a mismatch — including an older plan with no `Source spec:` line — stop and ask the user whether to archive or replace it; never silently execute a plan generated from a different spec.
4. **Single checkpoint.** Present the full plan and wait for an unambiguous affirmative (e.g. "approve", "go", "yes"). Treat hedged responses ("looks reasonable", "I guess") as **not** approved. This is the only human gate — after approval, run autonomously. If you generated `tasks/plan.md`, commit it as a single preparatory commit now so it doesn't bleed into the first task's commit.
5. **Execute every task in dependency order.** Use each task's declared dependencies; if they aren't explicit, execute in the order the plan lists them. For each task, run the full default loop above (RED → GREEN → regression → build → commit → mark complete). Stage only the files that task touched plus its task-status update — never `git add -A` blindly — and make one commit per task so any point is a clean rollback.
6. **Stop and ask the user** (do not push through) when:
   - a test can't be made to pass or the build breaks without an obvious fix → follow agent-skills:debugging-and-error-recovery
   - the spec is ambiguous, or a task needs a decision the spec doesn't cover
   - a task is high-risk or irreversible — auth/permission changes, destructive data migrations, payments, deletions, deploys, anything touching secrets, **or anything you can't undo with `git revert`** → follow agent-skills:doubt-driven-development and get explicit sign-off before continuing

   After the user resolves a blocker, they re-invoke `/build auto` — it resumes from the next pending task.
7. **Summarize at the end:** tasks completed, tests added, commits made, and anything skipped, flagged, or left for the user.

If any step fails, follow the agent-skills:debugging-and-error-recovery skill.
