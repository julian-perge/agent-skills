# Workflow

This repo keeps its tasks in `tasks/todo.md` and its specs in `spec/`, as [spec/helpers-map.md](../../spec/helpers-map.md) says. This file holds what `agent-skills land` reads.

## Checks

`agent-skills land <pr>` runs each command below on the PR branch, in this order, and merges only when all of them pass.

- `env PYTHONPATH=scripts python3 -m unittest discover -s scripts/agent_skills/tests`
- `node scripts/validate-skills.js`
- `node scripts/validate-commands.js`
- `node scripts/validate-reference-links.js`
- `node scripts/validate-artifact-paths.js`
- `node scripts/validate-versions.js`
- `node scripts/run-evals.js --min-rank1 95`
