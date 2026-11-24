# Spec: land, V1

Module of [helpers-map.md](helpers-map.md), slice 4. It inherits the tech stack, commands, code style and boundaries there. Source: items 3 and 4 of the runbook "Unattended agent sessions: turning my corrections into checks" (2026-11-21), its decision 2, and Julian's answers of 2026-11-22. It changes shipped behavior of stage-wiring (the `build` and `review` commands, the workflow seed) and of the merge rule in the map.

## Objective

Two things held Julian at the keyboard after a review passed:

- **The merge and the sync.** Between 2026-11-12 and 2026-11-18 he typed "merge it, checkout and pull main" or a like message 65 times in 63 sessions. One review said "ready to merge" for a PR that had merge conflicts.
- **The screenshot.** He asked "show me a screenshot" for urchin PR #326 and PR #328, which changed what the game draws and showed no image.

After this module, the session that finishes a review merges the pull request itself with one command, and that command refuses a pull request that is not proven. A pull request that changes what the user sees must show an image.

## Interface

Both verbs read `docs/agents/workflow.md` from `origin/<base>` of the pull request, after a `git fetch --prune origin`. A pull request can therefore not change the rules it is judged by. Two cases print a note on stderr: the base branch has no such file yet, and then the file of the checkout is read, or the pull request changes the file. With no file in either place, or in a clone that has no `origin/<base>`, the verbs exit 2. `evidence --add` reads no rules.

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

- **A list item** under the two headings is `- ` or `* `, then one span in backticks, and nothing after it. Lines that are not list items are prose for the reader. A heading inside a fenced code block is not a heading.
- **A list item that cannot be read** makes both verbs exit 2 and print the line. A skipped line would be a check that never runs. These are: a `+` or a numbered item, text after the span, a command that is empty, that `shlex` cannot split or that has a shell word such as `&&` or `|`, a glob that starts with `/` or `./` or uses `[`, `{` or a backslash, and a `<placeholder>` of the seed.
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
   - The working tree has changes to tracked files, also inside a submodule, whatever the git config hides.
   - The PR branch is behind `origin/<base>`, after a fetch. The checks would then not test the code that the merge makes.
   - The pull request has merge conflicts, or `mergeable` is still `UNKNOWN`.
   - No comment has the first line `Decisions from the review of PR #<PR>`, after any leading `#`, `*` and spaces and with nothing after the number. The comments of the pull request, of each issue it closes (up to 50) and of their parents are read (the last 50 of each).
   - The newest such comment, by the time GitHub gives, has no `Reviewed head: <full sha>` line or no `Reviewer: <text>` line. The message names the `decide` command that writes both.
   - The review does not cover the change at the PR head (see Review freshness below).
   - `evidence` would exit 1.
   - The file has no command under `## Checks`.
   - The sync after the merge would fail: the base branch is checked out in another worktree, or the local base branch has commits that neither `origin/<base>` nor the pull request holds.
   **Review freshness.** When the `Reviewed head:` sha is the PR head, the review counts. Otherwise `land` fetches each of the two commits that the clone lacks with `git fetch origin <sha>`, and computes the patch-id of the PR change at each: `git diff $(git merge-base origin/<base> <sha>) <sha> | git patch-id --verbatim`. `--verbatim` keeps whitespace, because `--stable` gives one id to a change and its re-indented copy, and indentation changes what Python code does. Equal patch-ids mean a rebase or a merge of the base branch that did not change the PR's own diff: the review counts, and a note on stderr says so. Different patch-ids give the line "the review covers <short sha>, but the PR head is <short sha> and its change differs. Review the PR again and post the decision with `agent-skills decide`." A commit that the fetch cannot get gives a line that says so. pstack's Shipping playbook has the same rule: a verdict holds for one patch-id, and only from an agent that did not write the code.
3. **Checks.** Each command under `## Checks` runs through the run wrapper, in the repo root, with no shell, in order. The first one that fails stops the verb with exit 1. After the checks, changed tracked files or a moved `HEAD` also stop it with exit 1.
4. **Merge:** `gh pr merge PR --repo OWNER/REPO --merge --delete-branch --match-head-commit <head commit>`. A merge commit keeps the commit ids that pull request bodies and decision comments cite, and one commit per task of `/build auto`. `--match-head-commit` makes GitHub refuse when the branch moved after the checks. The exit code of `gh` is not trusted in either direction, so `land` then reads the state of the pull request. `gh` merges first and deletes the remote branch second: when it fails and the pull request is merged all the same, `land` prints a note and goes on. When `gh` ends without an error and the pull request is not merged, as a merge queue can do, `land` exits 2 and leaves the checkout as it was.
5. **Sync.** It starts with `git fetch --prune origin`, which also drops the remote-tracking ref of the merged branch.
   - In the main checkout: `git switch <base>`, `git merge --ff-only origin/<base>`, `git branch -D <PR branch>`.
   - In a linked worktree: the main checkout is fast-forwarded when it is on the base branch, and left alone when it is on another branch. The worktree is removed with `git worktree remove --force`, and then the branch is deleted. `--force` is needed for a worktree with a submodule.
   - **What stays:** a worktree with a changed or an untracked file, also inside a submodule and whatever the git config hides. A worktree whose submodule holds a commit, a branch or a stash that none of its remotes has, because a linked worktree keeps the git folders of its submodules inside itself. A worktree or a branch that is no longer at the merged commit. The output says why, and for a worktree it gives the command that removes it.
   - **What goes without a question:** git-ignored files of a removed worktree. The output names the first 5 paths and counts the rest.
   - The output is `Landed PR #<PR> into <base>: <url>`, then one line per thing done.
6. **A failure after the merge** exits 2, and its message starts with `PR #<PR> is merged, but the checkout is not synced:`.

### `decide N --from review`

- `--reviewer <text>` is required. Without it, `decide` exits 1 and posts nothing. The other stages refuse the option with exit 2.
- The comment gets two lines right after its heading: `Reviewed head: <sha>`, the PR head that `gh pr view <PR> --json headRefOid` reports when `decide` runs, and `Reviewer: <text>`. A review decision without `--pr` or `--reviewer` exits 1 and posts nothing.
- The reviewer identity is recorded, not verified. `land` reads the line and does not check which agent or account posted the comment. The rule that the reviewer did not write the code is kept by the stage commands, not by a check.

### The stage commands and the seed

- **`review`:** step 1 runs `evidence`, and exit 1 is a Required finding that the review fixes. Step 6 posts a decision comment in every review, also with no finding. The decision comes from an agent that did not write the code at the reviewed head: when the review session committed fixes, an `agent-skills:code-reviewer` subagent reviews them and posts it. Step 8 runs `land` without asking, unless a choice still waits for the user.
- **`build`:** it runs `evidence` after the pull request is open, and it runs `land` after it finishes the review that its subagent started. The reviewer subagent posts the review decision, with `--reviewer "agent-skills:code-reviewer subagent"`, only when it applied no finding. When it applied findings, or the build session pushes after the decision, a new reviewer subagent reviews the new head and posts a new decision, unless the patch-id of the PR change is the same.
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

- **Rules:** unit tests of the glob rules, the two headings, the Verification section, the body edit and each refusal, also a review decision without one of its two lines and an older full comment behind a newer one that lacks a line.
- **Review freshness:** real git. A review of the head lands with no note. A rebase onto a moved base and a merge of the base keep the review, with a note. A new commit on the branch, and a reviewed sha that the fetch cannot get, are refused.
- **`land` and `evidence --add`:** `cli.main` with real git against a local bare repo (`tests/gitrepo.py`). Only `gh` is faked, and its fake merge really merges on the bare repo. The tests look at the repos afterwards: the branch, the worktree, the index file, the evidence branch. The checks are real `python3 -c` children that write a marker file, so a test can prove that no check ran.
- **`evidence`:** `cli.main` with the fake runner.
- **Hermetic:** the tests that run git drop every `GIT_*` variable of the caller and read no user or system git config, so a run inside a commit hook cannot write to the repo around it.
- **Mutants:** 39 one-line changes of the gate, the sync and the push each fail at least one test (2026-11-22).
- **No test writes to GitHub.**

## Success criteria

1. With the two headings above, `evidence` exits 1 for the recorded responses of urchin PR #326 and PR #328, and names the verify command.
2. After `evidence --add`, the index file, the status and `HEAD` of the checkout are the same as before, no hook ran, and the new body differs from the old one only by the added image lines.
3. For each gate condition, `land` exits 1, runs no check, does not merge, and leaves the branches and files of both repos as they were. Only the fetch has run.
4. A failing check stops the later checks and the merge.
5. On a clean pull request the checkout ends on the base branch at the merge commit, with the PR branch and its remote-tracking ref gone. From a linked worktree, the worktree is gone too.
6. Real proof in julian-perge/agent-skills: `land` exits 1 on a throwaway pull request with a merge conflict. It lands the pull request of this module, and the checkout ends on an up-to-date `main` with the branch gone.

## Out of scope (deferred)

- **A merge method per repo.** Every repo gets a merge commit.
- **An update of a branch that is behind.** `land` refuses, and the session merges the base branch itself.
- **Base branch moves between the gate and the merge.** The window is the run time of the checks. A branch rule or CI closes it, and these repos have neither.
- **Pull requests from a fork, and a head branch that must outlive its pull request.** `land` deletes the head branch.
- **Proof of the reviewer.** `land` trusts the `Reviewer:` line. A session that wrote the code can still post a review decision that names a subagent.
- **A second run that only syncs.** After exit 2 "is merged, but the checkout is not synced", the user syncs by hand.
- **A timeout for the checks.**
- **Untracked files that the checks read.** A check can pass because of a file that is not in the pull request. A refusal would stop every checkout that holds scratch files.
- **A submodule commit that the pull request pins and no remote has.** `land` keeps the worktree that holds it, and does not refuse the merge.
- **A submodule that was deinit-ed in a linked worktree.** `git submodule foreach` skips it, so an unpushed commit in its git folder goes with the worktree.
- **Images inside an HTML comment or an indented code fence.** They count as images.
- **Videos as evidence.** GitHub does not show a video from a repo link.
- **Cleanup of the `evidence` branch.**
- **The `gh pr merge` ask of the dotfiles hook** (runbook decision 9), and the two headings in urchin and blender. Each is a change in another repo.

## Open questions

None.
