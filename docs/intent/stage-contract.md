# Intent: one stage contract for build and review

Status: confirmed by Julian on 2026-11-16 in an `interview-me` session.

## Evidence

An audit of the 46 Claude Code sessions in urchin and blender from 2026-11-15 19:00 to 2026-11-16 16:40 UTC found these problems:

- **Review findings.** 14 reviews handled their findings in different ways. Before Julian replied, 4 fixed nothing, 6 fixed items and left them uncommitted, 1 tried to push and auto mode blocked it, and 2 asked through AskUserQuestion with recommendations. Julian typed "prompt me with recommended selections" 4 times and "commit and push" 4 times. The review command says only "Categorize findings", and the brief says only "Fix small findings in the review session".
- **Decisions.** Julian asked 6 times for decisions to be posted. Decisions ended up in chat, PR bodies, commit messages, Claude memory or a git-ignored `tasks/plan.md`. The #82 outfit was written only to `tasks/plan.md` in a worktree that was removed before build #87 ran, so Julian typed it again. Julian answered "Start!" twice (build #215 and its review). The rule "Report every guess and every gap" sends reports to chat.
- **Acceptance criteria.** The 9 issues closed in that window (urchin #204, #209, #215, #216, #218 and blender #84, #85, #86, #90) have 42 AC boxes, and none is ticked. The reviews wrote "all criteria met" in chat. No command, skill or doc says who ticks the boxes.
- **Draft PRs.** urchin #281, #282 and #283 are drafts because the Claude desktop app tells its sessions "Create the pull request as a draft". CLI sessions opened ready PRs. No app setting changes this.
- **Commits.** Blender's brief says "Ask for approval of the exact reviewed commit", so every blender build asked before its commit. All 9 urchin builds committed, pushed and opened a PR without asking.

The session dumps and scripts are in `~/tmp/2026-11-16-session-audit/`.

## Confirmed intent

- **Outcome:** build and review sessions in every repo that uses the tracker workflow follow one contract, so a session's behavior does not depend on the repo or the session.
- **User:** Julian. He runs each stage and should only need to answer prompts. He should not need to type "commit and push", "post it" or "prompt me with recommendations".
- **Why now:** in 24 hours Julian typed those requests 14 times, answered two decisions twice, and saw draft PRs that looked unfinished.
- **Success:**
  - **Review.** The review fixes, commits and pushes each Required finding that has one clear fix. It puts all other findings to Julian in one AskUserQuestion: a Required finding that is a choice, and the Optional, Nit and FYI findings. Each finding gets a clear explanation and a recommended option. Then the review commits and pushes by default, and ticks the AC boxes it checked. A box that is not met becomes a finding.
  - **Build.** The build commits, pushes and opens the PR without asking. When a choice is pending (a change the user can see, or a "needs the user's decision" item), it asks first through AskUserQuestion with a recommendation, then commits and pushes. Blender keeps its reviewer run before the commit but stops asking for approval of the commit.
  - **Decisions.** Each decision Julian makes goes in a comment on the issue it belongs to: the task issue, or the parent issue when later tasks need it. The PR body links to it. Every brief prints those comments.
  - **PRs.** A PR opens ready for review, with no labels. A build runs `gh pr ready` if the app made a draft.
- **Constraint:** the shared rules live in the fork's `review` and `build` commands and in the `agent-skills` helpers. Each repo's `workflow.md` drops the lines that conflict. Merging stays Julian's call.
- **Also in scope:**
  - Mark urchin #282 and #283 ready.
  - Tick the met AC boxes on the 9 closed issues.
  - Post the decisions that stayed in chat as issue comments: #273's open `leveled` question, #204's half-pixel offset and #215's "Start!".
- **Out of scope:**
  - PR labels.
  - Auto-merge, and cleanup after a merge.
  - Any change to the stage order or to the idea, design, spec and plan stages.
  - The open decisions from the blender review of #87.
