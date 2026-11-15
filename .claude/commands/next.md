---
description: "List what to do next in a repo that /agent-skills:setup-workflow set up in GitHub mode: PRs to review, tasks to build, and issues to spec, plan or refine, each with the /agent-skills command to paste. Read-only."
disable-model-invocation: true
---

# What to do next

Read the tracker and print the next commands for the `/agent-skills` workflow. Each command has real issue, PR and file values, so the user pastes it into a new session with no edits.

This skill is read-only. It adds no label, assignee or comment, and it checks out no branch.

## 1. Preflight

Stop with a message in these cases:

- `docs/agents/workflow.md` does not exist. Tell the user to run `/agent-skills:setup-workflow`.
- The agent file's `## Workflow` block does not say that tasks are tracked in GitHub Issues. This skill does not support files mode.

Then find these values:

- **Repo**: `gh repo view --json nameWithOwner`.
- **Standard file**: `CODING_STANDARDS.md` when it exists, else `AGENTS.md`, else `CLAUDE.md`.
- **Spec files**: `ls spec/*.md`. Do not list `spec/old/`.

## 2. Read the tracker

Read all open issues with one GraphQL query. Page with `pageInfo` until `hasNextPage` is false.

```
gh api graphql -F owner=<owner> -F name=<repo> -f query='
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    issues(states: OPEN, first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body
        assignees(first: 1) { totalCount }
        labels(first: 20) { nodes { name } }
        parent { number body }
        subIssuesSummary { total completed }
        issueDependenciesSummary { blockedBy }
        closedByPullRequestsReferences(first: 5, includeClosedPrs: false) { nodes { number } }
      }
    }
  }
}'
```

Read the open PRs: `gh pr list --state open --json number,title,headRefName,body,isDraft,createdAt`.

## 3. Find the spec of an issue

Use the first rule that gives a path. Check that the path exists.

1. A `Spec` line or a `spec/...md` path in the issue's body.
2. A `spec/...md` path in the parent issue's body.
3. Exactly one file that matches `spec/<issue>-*.md` or `spec/<parent>-*.md`. Mark this row as a guess.

When rule 3 finds several files, do not choose one. Print the command without the `spec` part, and list the candidate files under the row, so the user can add one. When no rule gives a path, leave out the `spec` part. Some issues have no spec.

## 4. Sort into groups

Each open issue or PR goes into one group, in this order of priority.

| Group | Rows | Command |
| --- | --- | --- |
| Review | Every open PR that is not a draft. The task is the `Closes #<n>` issue in the PR body, or the issue number in the branch name. | `/agent-skills:review issue #<task>, PR #<pr>, spec <spec file>, standard <standard file>` |
| Build | Open issues labelled `ready-for-agent` with no assignee, no open blocker (`blockedBy` is 0) and no open PR that closes them. | `/agent-skills:build #<task>` |
| Plan | A spec file whose issue is open and that no sub-issue's body names. In a repo with one spec per issue, this is an open issue with a spec and no sub-issues. | `/agent-skills:plan #<issue>, spec <spec file>` |
| Spec | Open issues with no parent, no sub-issues and no spec, and none of the labels `ready-for-agent`, `ready-for-human`, `needs-info`, `needs-triage` and `wontfix`. | `/agent-skills:spec #<issue>` |
| Idea | Open issues labelled `needs-triage`. | `/agent-skills:idea-refine #<issue>` |

Every open PR counts as needing review, because reviews run in local sessions and leave no mark on GitHub.

For the Plan group, read the body of every sub-issue of the spec's issue, closed ones too: `gh api repos/<owner>/<repo>/issues/<issue>/sub_issues --paginate --jq '.[].body'`. Do this only for issues that have a spec file.

In the Build group, mark the **frontier task** of each parent: its lowest open task number. This matches the frontier query in `docs/agents/issue-tracker.md`.

## 5. Report

Print one table per group that has rows, in the order Review, Build, Plan, Spec, Idea. Each table shows up to five rows: number, title, and the command in backticks. Under each table, say how many rows were left out. Show Review rows oldest PR first, and Build rows with frontier tasks first, then by number.

Then print **Next**: the oldest PR in Review, or when Review is empty, the lowest frontier task in Build. Put its commands in one fenced block, ready to paste:

- For a review: `gh pr checkout <pr>` as a shell step, then the review command.
- For a build: the build command.

Last, list every guess: each spec found by rule 3, each PR whose task came from its branch name, and each PR with no task.
