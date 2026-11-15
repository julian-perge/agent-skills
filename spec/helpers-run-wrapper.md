# Spec: run-wrapper, V1

Module of [helpers-map.md](helpers-map.md). It inherits the tech stack, commands, code style and boundaries there.

## Objective

Agents pipe test runs into `tail` and `rg` to find the result. Counts from the audit:
- `uv run pytest | tail`: 1,091 uses.
- `scripts/test-blender.sh`: 665 uses.
- `prek run --all-files | tail`: 491 uses.
- urchin's headless GUT runs, filtered for `Passing Tests|Failing Tests|SCRIPT ERROR`.

When the tail is too short, the agent runs the whole suite again. One blender build session ran `test-blender.sh -k pick` four times, only to see `tail -25`, `-4`, `-6` and `-4`.

`agent-skills run -- <cmd>` runs the command once. It keeps the full output on disk and prints what the agent needs to decide the next step: the exit code, the result and failure lines, and the last lines.

## Interface

```
agent-skills run [--name LABEL] [--tail N] -- CMD [ARG...]
```

- **Execution:** the argv runs directly, with no shell. Set environment variables with `env VAR=value CMD`. Shell syntax needs an explicit `bash -c '...'`.
- **Log path:** `${TMPDIR:-/tmp}/agent-skills/runs/<repo>/<YYYYmmdd-HHMMSS>-<label>.log`.
  - `<repo>` is the base name of `git rev-parse --show-toplevel`, or `norepo` outside a repo.
  - `<label>` is `--name`, or else a slug of the first two words of the command, ignoring `env` and `VAR=value` words and path prefixes.
- **Log content:** stdout and stderr are merged in order and written line by line while the command runs, with ANSI escape codes removed.
- **Output:**
  1. Before the command starts: `log: <path>`. A run that the agent moves to the background, or one that its tool call times out on, can still be found.
  2. After the command ends: `exit <code> after <seconds>s: <command>`.
  3. `## Summary lines (<k>)`: at most 40 lines that match the summary patterns, in output order, without duplicates.
  4. `## Last <N> lines`: the last N lines (default 15).
- **Summary patterns** (fixed in `run.py`):

| Runner | Patterns |
| --- | --- |
| pytest | `^(FAILED\|ERROR) `, `^E  `, `=+ .*(passed\|failed\|error).* =+$`, `short test summary` |
| GUT | `Passing Tests`, `Failing Tests`, `Asserts`, `Risky`, `\[Failed\]`, `SCRIPT ERROR`, `Parse Error` |
| prek, pre-commit | `\.+Failed$`, `- hook id:`, `- exit code:` |
| any | `Traceback \(most recent call last\)`, `^\w*Error:`, `^error(\[\w+\])?:`, `^fatal:` |

- **Exit code:** the command's own exit code, so `&&` chains keep working. A command that is not found gives 127. A usage error of the wrapper gives 125. A command that a signal ends gives `128 + <signal>`. The wrapper forwards SIGINT and SIGTERM to the child.
- **No timeout of its own:** the host's tool timeout applies.

## Project structure

```
scripts/agent_skills/run.py                     the verb; cli.py registers it
scripts/agent_skills/tests/test_run.py
scripts/agent_skills/tests/fixtures/run/        trimmed real output of pytest, GUT, prek and test-blender.sh, with expected summaries
```

## Testing strategy

- **Summary tests:** feed each fixture output through the summary function and compare the result with its expected file.
- **Process tests:** run small `python3 -c` children that print a set number of lines, write ANSI codes, write to stderr, sleep, and exit with the codes 0, 1 and 3. Also run one missing command.
- **Log test:** a child that sleeps between lines. The test reads the log while the child is still running.

## Success criteria

1. For the four fixtures (a pytest failure, a GUT failure with `SCRIPT ERROR`, a prek failure, a passing `test-blender.sh` run), the summary holds the count line and every failure line, and at most 40 lines.
2. The exit codes 0, 1 and 3 pass through. A missing command gives 127, and a wrapper usage error gives 125.
3. The log exists while the command runs, and in the end it holds all output in order, with no ANSI codes.
4. The output of a passing run with 10,000 lines is under 60 lines.
5. Manual check in blender: one `agent-skills run -- env BLENDER_USER_RESOURCES="$PWD/.blender-test-profile" scripts/test-blender.sh -k pick` shows the counts and the failures. No second run is needed.

## Out of scope (deferred)

- **The per-repo `## Commands` table, and the `verify` and `test` verbs:** slice 2.
- **Log cleanup:** `$TMPDIR` is cleared at reboot.
- **JUnit XML parsing, colored output, parallel commands.**
- **Patterns for each repo's own tools, such as bodecomp:** they come with the per-repo scripts in slice 2.

## Open questions

None.
