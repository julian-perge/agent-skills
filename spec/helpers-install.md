# Spec: install, V1

Module of [helpers-map.md](helpers-map.md). It inherits the tech stack, code style and boundaries there.

## Objective

On this Mac, `~/code/agent-skills` is the only copy of the pack. Claude Code, Codex, OpenCode and the shell all use it, and an edit takes effect without a push. Other machines clone the fork to the same path. The two skills that live in dotfiles today move into the fork as commands:

| Today (dotfiles) | After (fork) |
| --- | --- |
| `skills/agent-skills-next/SKILL.md` | `/agent-skills:next` |
| `skills/setup-agent-skills-workflow/` (SKILL.md and 4 seed files) | `/agent-skills:setup-workflow`, seeds in `references/workflow/` |

The fork diverges from upstream on purpose, so its agent files must stop telling agents to open PRs against `addyosmani/agent-skills`.

## Changes in the fork

1. `.claude-plugin/marketplace.json`: set the plugin entry's `source` to `"./"`. Keep the marketplace name `addy-agent-skills`, because `agent-skills` is a reserved name in Claude Code and the plugin id `agent-skills@addy-agent-skills` then stays the same.
2. Add the command `next` in all three command directories, with the same `description`:
   - `.claude/commands/next.md`: the body of today's `agent-skills-next` SKILL.md, with `/setup-agent-skills-workflow` changed to `/agent-skills:setup-workflow`.
   - `.gemini/commands/next.toml` and `commands/next.toml`: a prompt of one paragraph that says the command needs Claude Code and the `agent-skills` CLI.
3. Add the command `setup-workflow` the same way. Its `.md` body is today's setup SKILL.md body, with these changes:
   - Seed links point at `${CLAUDE_PLUGIN_ROOT}/references/workflow/<file>`.
   - `/agent-skills-next` becomes `/agent-skills:next`.
4. Move the 4 seed files to `references/workflow/`: `workflow-github.md`, `workflow-files.md`, `issue-tracker-github.md` and `survey-prompt.md`. In `survey-prompt.md`, change the skill search path `~/.claude/plugins/cache/addy-agent-skills` to `~/code/agent-skills`. In `workflow-github.md`, change `/agent-skills-next` to `/agent-skills:next`.
5. `CLAUDE.md` and `AGENTS.md`: rewrite the scope note and the Pull Requests rules.
   - PRs target `julian-perge/agent-skills`, branch `main`.
   - Upstream changes come in with `git fetch upstream && git merge upstream/main`.
   - Delete the rules that say to search upstream PRs before opening one.

## Changes in dotfiles

1. `dot_claude/settings.json.tmpl`: the `addy-agent-skills` entry under `extraKnownMarketplaces` becomes `{"source": {"source": "directory", "path": "{{ .chezmoi.homeDir }}/code/agent-skills"}}`. Delete its `autoUpdate`.
2. `.chezmoiexternal.toml`: the entry clones `https://github.com/julian-perge/agent-skills.git` to `code/agent-skills`, with `pull.args = ["--ff-only"]`. A `{{ if ne .chezmoi.os "darwin" }}` block skips the entry on this Mac.
3. `dot_config/opencode/opencode.jsonc.tmpl`: the skills path becomes `{{ .chezmoi.homeDir }}/code/agent-skills/skills`.
4. Add `dot_local/bin/symlink_agent-skills.tmpl` with the target `{{ .chezmoi.homeDir }}/code/agent-skills/bin/agent-skills`. The target is missing until tracker-cli lands, and a link to a missing target is allowed.
5. Delete `skills/agent-skills-next/`, `skills/setup-agent-skills-workflow/`, `dot_claude/skills/symlink_agent-skills-next.tmpl`, `dot_claude/skills/symlink_setup-agent-skills-workflow.tmpl` and `dot_agents/skills/symlink_setup-agent-skills-workflow`.
6. `README.md` and `private_obsidian/AI Runbooks/agent-skills workflow guide.md`: the new command names, and the path `~/code/agent-skills` instead of `~/.local/share/agent-skills`.

## Steps outside both repos

These steps change files that no repo manages. Each one needs the user's approval.

1. `~/.codex/config.toml`: `[marketplaces.agent-skills]` becomes `source_type = "local"` and `source = "/Users/sweetjp/code/agent-skills"`. Codex reads `.agents/plugins/marketplace.json`, whose plugin source is already `local` `./`.
2. `chezmoi apply`.
3. When `~/.claude/plugins/known_marketplaces.json` still shows the `github` source after a new session, run `claude plugin marketplace remove addy-agent-skills`, then `claude plugin marketplace add ~/code/agent-skills`, then `claude plugin install agent-skills@addy-agent-skills`. The remove command also uninstalls the plugin and deletes its plugin data, so ask first.
4. Delete the old clone `~/.local/share/agent-skills`. Ask first.

## Commands

```
Fork checks:        see helpers-map.md
Marketplace source: jq '."addy-agent-skills".source' ~/.claude/plugins/known_marketplaces.json
Leftover refs:      rg -uu -n 'agent-skills-next|setup-agent-skills-workflow|local/share/agent-skills|addyosmani/agent-skills' ~/code/dotfiles --glob '!.git' --glob '!**/.feedback/**'
Template output:    chezmoi execute-template < ~/code/dotfiles/.chezmoiexternal.toml
Link:               readlink ~/.local/bin/agent-skills
```

## Project structure

```
.claude/commands/{next,setup-workflow}.md      Claude Code bodies
.gemini/commands/{next,setup-workflow}.toml    pointer prompts
commands/{next,setup-workflow}.toml            pointer prompts
references/workflow/                           the 4 seed files
```

## Testing strategy

No unit tests: this module moves files and changes configuration. Each success criterion below is a command or a check in a new session.

## Success criteria

1. The fork checks and `claude plugin validate .` pass.
2. The marketplace source command prints `"source": "directory"` with the path `/Users/sweetjp/code/agent-skills`.
3. In a new Claude Code session, `/agent-skills:next` and `/agent-skills:setup-workflow` exist. An edit to `.claude/commands/next.md` appears after `/reload-plugins`, with no version change.
4. Codex lists the agent-skills skills, and its plugin comes from the local source.
5. The generated `~/.config/opencode/opencode.jsonc` names `/Users/sweetjp/code/agent-skills/skills`.
6. `readlink ~/.local/bin/agent-skills` prints `/Users/sweetjp/code/agent-skills/bin/agent-skills`.
7. The leftover-refs command prints no hit in a live file.
8. The template-output command prints no agent-skills entry on this Mac.
9. `rg -n -i 'upstream' CLAUDE.md AGENTS.md` in the fork shows only the merge instruction.

## Assumptions to verify during the build

- Codex may copy a local plugin into `~/.codex/plugins/cache/agent-skills/<version>/`, so an edit would not reach Codex until the plugin is reinstalled. Check this, and if it is true, write the refresh command into the fork's `AGENTS.md`.
- chezmoi reads `.chezmoiexternal.toml` as a template. Criterion 8 shows whether it does.
- `validate-artifact-paths.js` accepts the moved setup text, which names `spec/<issue>-<slug>.md` and `tasks/plan.md`. Criterion 1 shows whether it does.

## Out of scope (deferred)

- Renaming the marketplace or the plugin: the ids would change in every settings file.
- A version scheme of the fork's own: the manifests keep upstream's version numbers.
- A GitHub Action that merges upstream on a schedule.
- Full Gemini and Antigravity bodies: those hosts are not used.
- Proof on a Linux machine: the next `chezmoi apply` on a Linux machine checks the external clone.

## Open questions

None.
