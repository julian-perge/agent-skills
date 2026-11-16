# Using agent-skills with Codex

This repository is also a [Codex plugin](https://developers.openai.com/codex/plugins/build). The same root-level `skills/` directory used by Claude Code is consumed by Codex, so no files are copied or duplicated.

## Install

```bash
codex plugin marketplace add addyosmani/agent-skills
codex plugin add agent-skills@agent-skills
```

> Requires Codex CLI v0.122 or later. On older releases the command was `codex marketplace add`. See the [Codex CLI docs](https://developers.openai.com/codex/cli).

The first command registers this repository as the `agent-skills` marketplace. The second command installs and enables the `agent-skills` plugin from that marketplace. Start a new Codex session after installation so the skills are discovered.

Local clones work too:

```bash
codex plugin marketplace add /path/to/your/clone
codex plugin add agent-skills@agent-skills
```

## Usage

After install, invoke a skill in Codex chat with `@` (e.g. `@spec-driven-development`) or just describe the task and let Codex pick the right skill. All 25 skills under `skills/` are available.

[Codex uses progressive disclosure](https://developers.openai.com/codex/skills): it starts with each skill's `name` and `description`, chooses skills on demand, then loads the full `SKILL.md` only when selected. Do not also paste `using-agent-skills/SKILL.md` into `AGENTS.md`, a system prompt, or other always-on context: that stacks the pack's meta-router on Codex's native router and adds unnecessary routing work. The meta-skill can remain installed with the pack; the warning is specifically against preloading its full instructions.

## How it works

- `.codex-plugin/plugin.json` — Codex plugin manifest at the repo root. Points `skills` at `./skills/` and provides the metadata required by Codex.
- `.agents/plugins/marketplace.json` — marketplace entry declaring the repo root (`./`) as the plugin source.
- `skills/<name>/SKILL.md` — unchanged. Codex and Claude Code share the same `name` + `description` frontmatter format, so one file serves both platforms.

Personas in `agents/` stay Claude Code-specific. The `SessionStart` script under `hooks/` is a standalone helper for hosts without native skill routing and is not wired by either plugin.

## Commands

Codex loads skills but not the slash commands in `.claude/commands/`. So each command has an entry skill, `skills/cmd-<name>/`, that tells Codex to read the command file and follow it. Type the entry skill where you would type the slash command in Claude Code:

| Claude Code | Codex |
|---|---|
| `/agent-skills:build #226` | `$agent-skills:cmd-build #226` |
| `/agent-skills:review issue #219, PR #290` | `$agent-skills:cmd-review issue #219, PR #290` |
| `/agent-skills:<name> <arguments>` | `$agent-skills:cmd-<name> <arguments>` |

Codex never picks an entry skill by itself, because its `agents/openai.yaml` turns off implicit invocation. Claude Code does not list the entry skills, because their frontmatter sets `disable-model-invocation` and `user-invocable`. When you add a command, add its entry skill too: `node scripts/validate-commands.js` fails without it.
