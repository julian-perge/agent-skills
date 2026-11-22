# Capability Map: agent-skills helpers, slice 1

Source idea: [docs/ideas/agent-skills-helpers.md](../docs/ideas/agent-skills-helpers.md). Status: approved by the user on 2026-11-15. Module specs approved on 2026-11-15.

| Module id | Responsibility | Depends on | Spec |
| --- | --- | --- | --- |
| install | `~/code/agent-skills` is the one copy that Claude Code, Codex, OpenCode and the shell use. The two dotfiles skills become the commands `/agent-skills:next` and `/agent-skills:setup-workflow`. Dotfiles keeps no copy. The fork's agent files stop sending PRs upstream. | - | [helpers-install.md](helpers-install.md) |
| tracker-cli | `bin/agent-skills` and the verbs `next`, `issue`, `pr`, `claim`, `frontier` and `next-cmd`, with unit tests on recorded `gh` responses. | - | [helpers-tracker-cli.md](helpers-tracker-cli.md) |
| run-wrapper | The verb `run`: one run of a test, lint or build command, the full log on disk, and a short summary. | tracker-cli (the entry point only) | [helpers-run-wrapper.md](helpers-run-wrapper.md) |
| stage-wiring | The stage commands and the workflow seeds call the verbs. Two `enforce-tools.sh` rules block the known-bad `gh` forms. urchin and blender get refreshed workflow docs. | install, tracker-cli, run-wrapper | [helpers-stage-wiring.md](helpers-stage-wiring.md) |

Build order: install and tracker-cli (in either order), then run-wrapper, then stage-wiring.

### Slice 2

| Module id | Responsibility | Depends on | Spec |
| --- | --- | --- | --- |
| stage-brief | The verb `brief`: the `workflow.md` sections that one stage needs, then the issue or PR brief, in one call. The stage commands, the setup template, urchin and blender start each stage with it. | tracker-cli, stage-wiring | [helpers-stage-brief.md](helpers-stage-brief.md) |

### Slice 3

Done on 2026-11-16.

| Module id | Responsibility | Depends on | Spec |
| --- | --- | --- | --- |
| stage-contract | One contract for build and review: how findings are fixed, asked about and committed, decision comments on issues (the verb `decide`, and a Decisions section in `issue`), AC boxes ticked by the review (the verb `ac`), ready PRs, and the cleanup in urchin and blender. Source: [docs/intent/stage-contract.md](../docs/intent/stage-contract.md). | tracker-cli, stage-brief, stage-wiring | [helpers-stage-contract.md](helpers-stage-contract.md) |

### Slice 4

| Module id | Responsibility | Depends on | Spec |
| --- | --- | --- | --- |
| land | The verbs `evidence` and `land`: a pull request that changes what the user sees must show an image, and the session that finishes a review merges with one command that runs the checks first and then syncs the checkout. | tracker-cli, run-wrapper, stage-contract | [helpers-land.md](helpers-land.md) |

## Interfaces at the boundaries

- **install provides paths.** The fork is at `~/code/agent-skills` on every machine. `agent-skills` is on the PATH of Claude Code (plugin `bin/`), Codex and OpenCode (`~/.local/bin/agent-skills`).
- **tracker-cli provides the entry point.** `bin/agent-skills <verb>` dispatches to `scripts/agent_skills/cli.py`. run-wrapper adds one verb to the same dispatcher and shares nothing else.
- **stage-wiring uses verbs by name only.** It relies on the output contracts in the tracker-cli and run-wrapper specs, not on their code.

## Shared conventions

Every module spec inherits this section and states only its differences.

### Tech stack

- Python 3.11 or later, standard library only. Every script starts with `#!/usr/bin/env python3` and a PEP 723 block with `dependencies = []`, so `python3` and `uv run` both work.
- `gh` 2.94 or later (sub-issue support) and `git`.
- The fork's existing Node validators stay as they are.

### Commands

Run from `~/code/agent-skills`:

```
Unit tests:      PYTHONPATH=scripts python3 -m unittest discover -s scripts/agent_skills/tests
Fork checks:     node scripts/validate-skills.js && node scripts/validate-commands.js && node scripts/validate-reference-links.js && node scripts/validate-artifact-paths.js && node scripts/run-evals.js --min-rank1 95
Plugin check:    claude plugin validate .
CLI smoke check: bin/agent-skills --help
```

### Code style

Rules are pure functions on parsed data. Only `scripts/agent_skills/github.py` runs `gh` or `git`. Output text is built in `render.py`. Errors raise `CliError`, and `cli.main()` prints the message to stderr and exits with its code.

```python
@dataclass(frozen=True)
class SpecMatch:
    path: str | None
    source: str
    guess: bool
    candidates: tuple[str, ...] = ()


def spec_for(issue: Issue, spec_files: frozenset[str]) -> SpecMatch:
    for text, source in ((issue.body, "issue body"), (issue.parent_body, "parent body")):
        path = first_spec_path(text)
        if path in spec_files:
            return SpecMatch(path, source, guess=False)
    numbers = {issue.number, issue.parent_number}
    candidates = tuple(sorted(p for p in spec_files if spec_number(p) in numbers))
    if len(candidates) == 1:
        return SpecMatch(candidates[0], "file name", guess=True)
    return SpecMatch(None, "none", guess=False, candidates=candidates)
```

Naming: modules and functions in `snake_case`, verbs in `kebab-case`. Type hints on every function. No comments that restate the code (see the comment rules in `~/.claude/CLAUDE.md`).

### Boundaries

- **Always:** run the unit tests and the fork checks before each commit. Pass `--repo <owner>/<repo>` of `origin` on every `gh` call. Mark every guess in the output with `(guess)`.
- **Ask first:** a verb or flag that no spec names. A CI change other than the one unit-test step in tracker-cli. Deleting anything outside the repos named in a spec.
- **Never:** write to GitHub from a test. Add a third-party Python dependency. Merge a PR, except with `agent-skills land`.
