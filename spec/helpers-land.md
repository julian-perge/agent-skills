# Spec: land, V1

Module of [helpers-map.md](helpers-map.md), slice 4. It inherits the tech stack, commands, code style and boundaries there. Source: items 3 and 4 of the runbook "Unattended agent sessions: turning my corrections into checks" (2026-11-21), its decision 2, and Julian's answers of 2026-11-22. It changes shipped behavior of stage-wiring (the `build` and `review` commands, the workflow seed) and of the merge rule in the map.

## Objective

Two things held Julian at the keyboard after a review passed:

- **The merge and the sync.** Between 2026-11-12 and 2026-11-18 he typed "merge it, checkout and pull main" or a like message 65 times in 63 sessions. One review said "ready to merge" for a PR that had merge conflicts.
- **The screenshot.** He asked "show me a screenshot" for urchin PR #326 and PR #328, which changed what the game draws and showed no image.

After this module, the session that finishes a review merges the pull request itself with one command, and that command refuses a pull request that is not proven. A pull request that changes what the user sees must show an image.

## Interface

Both verbs read `docs/agents/workflow.md` from `origin/<base>` of the pull request, after a `git fetch --prune origin`. A pull request can therefore not change the rules it is judged by. Two cases print a note on stderr: the base branch has no such file yet, and then the file of the checkout is read, or the pull request changes the file. With no file in either place the verbs exit 2. `evidence --add` reads no rules.

### Two headings in `docs/agents/workflow.md`

```
## Checks

- `just gut`
- `just pytest`

## Evidence paths

Verify command: the verify-urchin skill

- `scenes/**`
- `scripts/ui/**`
```

- **A list item** under the two headings is `- ` or `* `, then one span in backticks, and nothing after it. Lines that are not list items are prose for the reader.
- **A list item that cannot be read** makes both verbs exit 2 and print the line: text after the span, a command that `shlex` cannot split, a glob that starts with `/` or `./` or uses `[`, or a `<placeholder>` of the seed. A skipped line would be a check that never runs.
- **Glob rules:** a glob must match the whole path from the repo root. `*` and `?` stay inside one path part. `**` crosses parts, and `**/` at the start or after a `/` also matches no folder. A glob that ends with `/` covers the whole folder.
- **`Verify command:`** is one line of free text. The refusal of `evidence` prints it.
- A heading matches without case. `brief` prints both sections for the build, bug and review stages.

### `evidence PR`

- One `gh api graphql` call reads the pull request: its body, its changed paths and the fields that `land` needs. When the pull request changes more than 100 files, a second call reads all paths from `repos/OWNER/REPO/pulls/PR/files`.
- **Exit 0** when the file has no `## Evidence paths` heading, when the pull request changes none of those paths, or when its body has a Verification section with an image. The output is one line that says which.
- **Exit 1** when the pull request changes an evidence path and its body has no Verification section with an image. The message names up to 3 of the paths, the verify command and the `--add` form.
- **The Verification section** is a heading of any level whose text starts with `Verification`, up to the next heading of the same or a higher level. A line that starts with `#` inside a fenced code block is not a heading.
- **An image** is `![alt](url)` or an `<img ... src=` tag with an `http` or `https` URL, outside code spans and fenced code blocks. A local path and a plain link do not count: the reader must see the image in the pull request.

### `evidence PR --add IMAGE...`

- **Refused (exit 1, nothing written):** a path that is not a file, a suffix other than `.png`, `.jpg`, `.jpeg`, `.gif` or `.webp`, two files with one name, or a `--repo` that is not `origin` (the images would go to one repo and the links to another).
- **Push:** the files go to `pr-<PR>/<name>` on the `evidence` branch of `origin`, in one new commit on top of the branch, or as its first commit. The commit is built with `git hash-object`, a scratch index file and `git commit-tree`, and pushed with `--no-verify`, so the checkout, its index and its hooks are not used. The push is not forced: when another session pushed in the meantime, the verb exits 2 and the other commit stays. `main` gets no binary file.
- **Body:** each image is added as `![<file stem>](https://github.com/OWNER/REPO/blob/<commit>/pr-<PR>/<name>?raw=true)` at the end of the Verification section, with `[` and `]` of the stem written as `(` and `)`. A body without the section gets `## Verification` at its end. The URL names the commit, so a later push does not change what the pull request shows. Every other line keeps its text and its own line end, and blank lines at the end of the section become one.
- **Lost update:** the body is read again before the write. When it changed, the verb exits 1, says that the images are pushed, and does not edit.
- **Output:** one line with the count, the branch and the commit, then one URL per line.

### `land PR`

Run it on the PR branch. It works in this order:

1. **Read** the pull request. GitHub works out `mergeable` in the background, so an `UNKNOWN` is read again, up to 4 times, 2 seconds apart.
2. **Gate.** Each failed condition is one line under `Not landed: PR #<PR>` on stderr, the exit code is 1, and no check runs:
   - The pull request is not open (this is then the only line), or it is a draft.
   - The checkout is not on the PR branch, or `HEAD` is not the head commit of the pull request.
   - The working tree has changes to tracked files.
   - The PR branch is behind `origin/<base>`, after a fetch. The checks would then not test the code that the merge makes.
   - The pull request has merge conflicts, or `mergeable` is still `UNKNOWN`.
   - No comment has the first line `Decisions from the review of PR #<PR>`, after any leading `#`, `*` and spaces and with nothing after the number. The comments of the pull request, of each issue it closes (up to 50) and of their parents are read (the last 50 of each).
   - `evidence` would exit 1.
   - The file has no command under `## Checks`.
3. **Checks.** Each command under `## Checks` runs through the run wrapper, in the repo root, with no shell, in order. The first one that fails stops the verb with exit 1. After the checks, changed tracked files or a moved `HEAD` also stop it with exit 1.
4. **Merge:** `gh pr merge PR --repo OWNER/REPO --merge --delete-branch --match-head-commit <head commit>`. A merge commit keeps the commit ids that pull request bodies and decision comments cite, and one commit per task of `/build auto`. `--match-head-commit` makes GitHub refuse when the branch moved after the checks. `gh` merges first and deletes the remote branch second. When it fails and the pull request is merged all the same, `land` prints a note and goes on.
5. **Sync.** It starts with `git fetch --prune origin`, which also drops the remote-tracking ref of the merged branch.
   - In the main checkout: `git switch <base>`, `git merge --ff-only origin/<base>`, `git branch -D <PR branch>`.
   - In a linked worktree: the main checkout is fast-forwarded when it is on the base branch, and left alone when it is on another branch. The worktree is removed with `git worktree remove --force`, and then the branch is deleted. `--force` is needed for a worktree with a submodule.
   - **What stays:** a worktree with a changed or an untracked file, also inside a submodule, and a worktree or a branch that is no longer at the merged commit. The output says why and gives the command that removes it.
   - **What goes without a question:** git-ignored files of a removed worktree. The output names the first 5 paths and counts the rest.
   - The output is `Landed PR #<PR> into <base>: <url>`, then one line per thing done.
6. **A failure after the merge** exits 2, and its message starts with `PR #<PR> is merged, but the checkout is not synced:`.

### The stage commands and the seed

- **`review`:** step 1 runs `evidence`, and exit 1 is a Required finding that the review fixes. Step 6 posts a decision comment in every review, also with no finding. Step 8 runs `land` without asking, unless a choice still waits for the user.
- **`build`:** it runs `evidence` after the pull request is open, and it runs `land` after it finishes the review that its subagent started.
- **`references/workflow/workflow-github.md`:** the two verbs in the Helpers table, the land rule under Build and Review, and the `## Checks` and `## Evidence paths` sections. `setup-workflow` fills both sections.
- **Merge rule:** a session may merge only with `land`. It replaces "the user merges, unless the user's own message says otherwise".

## Project structure

```
scripts/agent_skills/land.py                 the rules of both verbs, as pure functions
scripts/agent_skills/github.py               LAND_QUERY, the push to the evidence branch, the merge and the sync calls
scripts/agent_skills/cli.py                  the verbs evidence and land
scripts/agent_skills/tests/test_evidence.py
scripts/agent_skills/tests/test_land.py
scripts/agent_skills/tests/fixtures/land-urchin-326.json, land-urchin-328.json   trimmed real responses
```

## Testing strategy

- **Rules:** unit tests of the glob rules, the two headings, the Verification section, the body edit and each refusal.
- **`land` and `evidence --add`:** `cli.main` with real git against a local bare repo (`tests/gitrepo.py`). Only `gh` is faked, and its fake merge really merges on the bare repo. The tests look at the repos afterwards: the branch, the worktree, the index file, the evidence branch. The checks are real `python3 -c` children that write a marker file, so a test can prove that no check ran.
- **`evidence`:** `cli.main` with the fake runner.
- **Mutants:** 27 one-line changes of the gate, the sync and the push each fail at least one test (2026-11-22).
- **No test writes to GitHub.**

## Success criteria

1. With the two headings above, `evidence` exits 1 for the recorded responses of urchin PR #326 and PR #328, and names the verify command.
2. After `evidence --add`, the index file, the status and `HEAD` of the checkout are the same as before, no hook ran, and the new body differs from the old one only by the added image lines.
3. For each gate condition, `land` exits 1, runs no check, does not merge, and leaves both repos as they were.
4. A failing check stops the later checks and the merge.
5. On a clean pull request the checkout ends on the base branch at the merge commit, with the PR branch and its remote-tracking ref gone. From a linked worktree, the worktree is gone too.
6. Real proof in julian-perge/agent-skills: `land` exits 1 on a throwaway pull request with a merge conflict. It lands the pull request of this module, and the checkout ends on an up-to-date `main` with the branch gone.

## Out of scope (deferred)

- **A merge method per repo.** Every repo gets a merge commit.
- **An update of a branch that is behind.** `land` refuses, and the session merges the base branch itself.
- **Base branch moves between the gate and the merge.** The window is the run time of the checks. A branch rule or CI closes it, and these repos have neither.
- **Pull requests from a fork, and a head branch that must outlive its pull request.** `land` deletes the head branch.
- **A decision comment that is older than the last commit.** `land` does not compare the two.
- **A second run that only syncs.** After exit 2 "is merged, but the checkout is not synced", the user syncs by hand.
- **A timeout for the checks.**
- **Videos as evidence.** GitHub does not show a video from a repo link.
- **Cleanup of the `evidence` branch.**
- **The `gh pr merge` ask of the dotfiles hook** (runbook decision 9), and the two headings in urchin and blender. Each is a change in another repo.

## Open questions

None.
