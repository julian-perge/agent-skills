---
description: Run TDD workflow — write failing tests, implement, verify. For bugs, use the Prove-It pattern.
disable-model-invocation: true
---

Invoke the agent-skills:test-driven-development skill.

In a repo whose `docs/agents/workflow.md` tracks tasks in GitHub Issues, start with `agent-skills brief test <n>` and read its whole output, with no `head` or `tail` (add `--full` for all comments and sub-issues).

For new features:
1. Write tests that describe the expected behavior (they should FAIL)
2. Implement the code to make them pass
3. Refactor while keeping tests green

For bug fixes (Prove-It pattern):
1. Write a test that reproduces the bug (must FAIL)
2. Confirm the test fails
3. Implement the fix
4. Confirm the test passes
5. Run the full test suite for regressions

For browser-related issues, also invoke agent-skills:browser-testing-with-devtools to verify with Chrome DevTools MCP.
