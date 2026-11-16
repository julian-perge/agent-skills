---
name: cmd-next
description: Runs the agent-skills /next command in Codex, which does not load Claude Code commands. Use when the user types $agent-skills:cmd-next.
disable-model-invocation: true
user-invocable: false
---

# /agent-skills:next in Codex

1. Read `.claude/commands/next.md` in the plugin root, which is two directories above this file. Read the whole file.
2. Follow that file as your instructions for this turn. The text the user typed after `$agent-skills:cmd-next` is its `$ARGUMENTS`.
3. Read a skill name such as `agent-skills:incremental-implementation` as the Codex skill of the same name. Read a command `/agent-skills:<name>`, such as `/agent-skills:review 290` in helper output, as `$agent-skills:cmd-<name>`, such as `$agent-skills:cmd-review 290`. Keep the `/agent-skills:` form in text that you post to GitHub, because Claude Code sessions read it too.
4. Where the file names a Claude Code tool that Codex does not have, do the same step with the closest Codex tool. For `AskUserQuestion`, ask the user in chat.
