---
name: mr
description: Push a branch and create or update its GitHub pull request with gh
---

## Purpose

Use when the user explicitly asks to open, create, or update a merge request or
pull request. In this repository the requested `mr` parity skill operates on
GitHub via `gh`; pushing and PR metadata changes are visible mutations covered
by that explicit request.

Never update a closed or merged PR. Match an existing PR by exact source head
branch and verify its state before writing; target it by PR number, not a branch
name. Preserve existing base, assignees, labels, reviewers, and other metadata
unless the user requests a change.

## Workflow

1. Resolve the source branch without checking it out. For an existing open PR,
   preserve its `baseRefName`. For a new PR, use an explicit user target first,
   otherwise read GitHub's default with
   `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name`. Fetch the
   selected remote ref and prove the relationship with `git merge-base`; do not
   guess from `origin/HEAD` or an unrelated branch name.
2. Inspect actual commits and `git diff <base>...<head>`. Run applicable QA via
   `.agents/scripts/qa-select` and `.agents/scripts/qa-run`; derive title, summary,
   test plan, and risks from those results, not assumptions. Before any push,
   run `.agents/scripts/protect-local --range <base>...<head>` and inspect the
   committed diff for private library facts; a clean working tree alone does
   not prove that the branch range is safe.
3. Before pushing, query all historical matches with
   `gh pr list --head <branch> --state all --json number,state,mergedAt,headRefName,baseRefName,url`.
   If an exact open-head PR exists, verify it with
   `gh pr view <number> --json state,headRefName,baseRefName,url`. If only a
   closed or merged match exists, stop before mutation and require a new branch
   name. Refuse a new PR whose head equals its base.
4. Push the exact branch with `git push -u origin <branch>`.
5. Create with `gh pr create` only when no historical PR uses that exact head;
   otherwise update the verified open exact-head PR by number with
   `gh pr edit <number>`. Do not touch closed or merged PRs.

Use the template in [references/pr-description.md](references/pr-description.md).
Keep title and body in English. Do not add tool-attribution lines or merge
policy flags such as auto-delete or squash unless requested.

## Report

Use `.agents/scripts/handoff`; include branch, base proof, PR URL/number, push
result, actual QA, and residual risk. This skill does not merge the PR.
