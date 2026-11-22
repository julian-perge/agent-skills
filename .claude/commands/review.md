---
description: Conduct a five-axis code review — correctness, readability, architecture, security, performance
disable-model-invocation: true
---

Invoke the agent-skills:code-review-and-quality skill.

In a repo whose `docs/agents/workflow.md` tracks tasks in GitHub Issues, start with `agent-skills brief review <pr>`, which prints the task issue and names the spec and the standard, and read its whole output, with no `head` or `tail` (add `--full` for the whole PR body). Run tests with `agent-skills run --`.

Review the current changes (staged or recent commits) across all five axes:

1. **Correctness** — Does it match the spec? Edge cases handled? Tests adequate?
2. **Readability** — Clear names? Straightforward logic? Well-organized?
3. **Architecture** — Follows existing patterns? Clean boundaries? Right abstraction level?
4. **Security** — Input validated? Secrets safe? Auth checked? (Use security-and-hardening skill)
5. **Performance** — No N+1 queries? No unbounded ops? (Use performance-optimization skill)

Categorize findings as Critical, Required, Optional, or Nit.
Output a structured review with specific file:line references and fix recommendations.

## In a repo that tracks tasks in GitHub Issues

Handle the findings in these steps. A finding is **yours to apply** when it changes nothing the user can see, the standard does not mark it "needs the user's decision", and its fix fits in this session. Apply it with its one reasonable fix, or with your recommended option when it has several fixes. Every other finding is a **choice**. The **question tool** is AskUserQuestion. In a host without one, write a numbered list with the recommended option first, then stop and wait.

1. Label each finding Critical, Required, Optional, Nit or FYI, and mark it as yours to apply or a choice. Check each acceptance criterion of the task. A criterion that is not met is a finding. Run `agent-skills evidence <pr>`. Exit 1 is a Required finding that is yours to apply: make the screenshots with the verify command it names, and add them with `agent-skills evidence <pr> --add <image>...`.
2. Apply every finding that is yours to apply, at every severity. Run the checks with `agent-skills run --`. Commit and push without asking.
3. Ask about every other finding with the question tool, one question per finding and at most 4 per call. Each question says where the finding is (`file:line`), what is wrong and what happens if it stays. Put the recommended option first. Give a finding that is too large for this session the option "File a follow-up issue".
4. Apply the answers. Run the checks. Commit and push, unless the user chose otherwise.
5. Tick each acceptance criterion that step 1 found met, with `agent-skills ac <task> --tick <list>`.
6. Post the decisions with `agent-skills decide <issue> --from review --pr <pr>`, with the body on stdin: each answer the user gave and its reason, then the guesses and gaps you accepted under `#### Guesses and gaps`. List there each finding from step 2 that had more than one fix, with the option you applied, so the user can revert it. Post on the task issue, or on the source issue when later tasks need the decision. When the session has nothing to record, post "No findings and no decisions.", because `agent-skills land` merges only a pull request that has this comment. When the pull request closes no issue, post on the pull request itself: `agent-skills decide <pr> --from review --pr <pr>`.
7. Fix each line of the PR body that the fixes made false, and add a line that links the decision comment.
8. When the review passes and its findings are fixed, run `agent-skills land <pr>` on the PR branch, without asking. It runs the checks of the repo, merges the pull request, moves the checkout to the base branch and deletes the PR branch. It exits 1 and merges nothing when its gate fails: fix what it names and run it again, or stop and report the reasons when a fix is not yours to apply. Exit 2 with "is merged, but the checkout is not synced" means the merge is done: report the message, and do not run `land` again. In a linked worktree, `land` removes the worktree, so change to the folder it names before the next command. Do not run `gh pr merge` yourself. When a choice still waits for the user, do not land. Then print the next stage's command as the last line.
