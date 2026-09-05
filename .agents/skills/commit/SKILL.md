---
name: commit
description: Create one scoped conventional Git commit after QA and staged-scope checks
---

## Purpose

Create a local commit only when the user explicitly asks to commit. A request
to implement, finish, wrap up, or report completion is not commit authorization.
This skill does not push, open a pull request, amend history, or broaden the
requested file scope.

## Before committing

1. Confirm the current branch and inspect `git status --short` and the relevant
   `git diff`; preserve unrelated worktree changes.
2. Run the focused QA required by the changed files. Pipe explicit paths to
   `.codex/scripts/qa-select`, then run the selected profile with
   `.codex/scripts/qa-run`.
3. Stage only the requested paths with explicit path arguments. Never use
   `git add .` or `git add -A`.
4. Run `.codex/scripts/staged-check <path> ...`; inspect `git diff --cached`.
   Protected local paths are never staged. Specs require explicit authorization
   in the current user turn and `DJ_DIGGER_ALLOW_SPEC_STAGE=1`; the environment
   variable alone is not authorization.

## Commit

Use the convention in [references/message-patterns.md](references/message-patterns.md).
The subject is English, imperative, and conventional; include a body with the
bounded worker brief (Goal, Changed files, Observed proof, Residual risk) when
the subject alone cannot explain a meaningful change. Do not add
`Co-Authored-By` or `Signed-off-by` trailers. Use `git commit` without
`--no-verify`; never amend unless the user explicitly authorizes it.

## Report

Finish with `.codex/scripts/handoff` and report the exact QA command, staged
paths, commit result, and any residual risk. A commit is not authorization to
push or open a pull request.
