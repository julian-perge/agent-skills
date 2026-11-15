---
description: "List what to do next in a repo that /agent-skills:setup-workflow set up in GitHub mode: PRs to review, tasks to build, and issues to spec, plan or refine, each with the /agent-skills command to paste. Read-only."
disable-model-invocation: true
---

# What to do next

Run `agent-skills next` from the repository root and print its output unchanged. It lists the PRs to review, the tasks to build and the issues to plan, spec or refine, each with the `/agent-skills` command to paste.

The command is read-only. It adds no label, assignee or comment, and it checks out no branch.

When `agent-skills next` exits with code 2, print its message and stop. The rules for the groups, the frontier and the spec lookup are in `scripts/agent_skills/tracker.py` and its tests, not here.
