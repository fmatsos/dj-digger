---
name: ship
description: Run QA, scoped commits, push, and GitHub pull-request checks for explicitly requested delivery
---

## Purpose

Use only when the user explicitly requests end-to-end delivery (for example,
“ship this” or “get this to a green PR”). Invocation authorizes the scoped
commit, push, PR create/update, and checks below; ordinary implementation does
not. Never broaden the diff or touch protected paths.

## Workflow

1. Record branch, remote, and base. Resolve an explicit base first, otherwise
   use the configured upstream/default branch and prove ancestry with
   `git merge-base`; do not guess. Use the `mr` skill's all-state lookup to
   confirm the branch is not reusing a closed or merged PR. If head equals base,
   create a descriptive non-colliding branch for this delivery, then repeat
   preflight; do not use a worktree.
2. Determine changed paths with `.agents/scripts/changed-files`, protect local
   data with `.agents/scripts/protect-local --changed`, select QA with
   `.agents/scripts/qa-select`, and run it with `.agents/scripts/qa-run`.
   Stop before mutation on red QA or inaccessible required dependencies.
3. Group the actual diff into scoped conventional commits. Stage paths
   explicitly, run `.agents/scripts/staged-check`, inspect the cached diff, and
   use `git commit` without `--no-verify` or amend. Recheck that repository-
   declared protected paths and ignored files are absent. Never force-stage
   ignored archives or local data.
4. Push `origin <branch>` and create or update the exact open-head PR with
   `gh`, following the `mr` skill and its description reference. Run
   `.agents/scripts/protect-local --range <base>...<branch>` immediately before
   pushing so already-committed protected files cannot escape. Preserve PR
   metadata unless requested; never force-push unless the user explicitly
   authorizes rewriting that branch.
5. Run `gh pr checks <number> --watch`. For actionable failures, identify the
   failed workflow/check from `gh pr checks <number> --json` and inspect its
   actual GitHub Actions log with `gh run view`; allow at most three repair
   rounds. Each repair reruns QA,
   makes a scoped commit, pushes, and watches checks again. Exit immediately
   for secrets, permissions, infrastructure, or external-service failures.

Read [assets/report.md](assets/report.md) for the final report shape. Finish
with `.agents/scripts/handoff`, including branch/base proof, commits, QA, PR,
check result, repair rounds, and residual risk. Do not merge or delete branches.
