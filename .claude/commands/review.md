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

Handle the findings in these steps. A **clear fix** is a finding with one reasonable fix, which changes nothing the user can see, and which the standard does not mark "needs the user's decision". Every other finding is a **choice**. The **question tool** is AskUserQuestion. In a host without one, write a numbered list with the recommended option first, then stop and wait.

1. Label each finding Critical, Required, Optional, Nit or FYI, and mark it as a clear fix or a choice. Check each acceptance criterion of the task. A criterion that is not met is a finding.
2. Fix the Critical and Required findings that are clear fixes. Run the checks with `agent-skills run --`. Commit and push without asking.
3. Ask about every other finding with the question tool, one question per finding and at most 4 per call. Each question says where the finding is (`file:line`), what is wrong and what happens if it stays. Put the recommended option first. Give a finding that is too large for this session the option "File a follow-up issue".
4. Apply the answers. Run the checks. Commit and push, unless the user chose otherwise.
5. Tick each acceptance criterion that step 1 found met, with `agent-skills ac <task> --tick <list>`.
6. Post the decisions with `agent-skills decide <issue> --from review --pr <pr>`, with the body on stdin: each answer the user gave and its reason, then the guesses and gaps you accepted under `#### Guesses and gaps`. Post on the task issue, or on the source issue when later tasks need the decision. Skip this step when the session has nothing to record.
7. Fix each line of the PR body that the fixes made false, and add a line that links the decision comment.
8. Print the next stage's command as the last line. Do not merge. The user merges.
