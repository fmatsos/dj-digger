---
name: ship
description: Staged diff check, commit, and push with explicit authorization and ancestry proof
---

## Purpose

Handles staged diffs, commits, and pushes. Requires explicit scope and authorization. Never stages with `.`, never deletes branches without proof, never stages specs without explicit approval.

## Pre-flight checks

1. **Explicit request**: User has explicitly requested commit/push.
2. **Staged scope**: Run `.claude/scripts/staged-check <file1> [<file2> ...]` for all staged files.
3. **No glob staging**: Confirm no `git add .` or `git add -A` used.
4. **No conflict markers**: Scan staged content for `<<<<<<<`, `=======`, `>>>>>>>`.
5. **Protected paths**: No staging of `config/local.toml`, `workspace/`, `sets/`, `*.sqlite*`, `docs/superpowers/specs/**`.
6. **Spec authorization**: Specs in `docs/superpowers/specs/**` require `DJ_DIGGER_ALLOW_SPEC_STAGE=1`.
7. **HEAD verification**: Confirm local HEAD matches expected commit.
8. **Remote HEAD**: Confirm remote main hasn't changed (pull to sync if needed).

## Commit workflow

1. **Diff review**: Show `git diff --cached` and confirm correctness.
2. **Message**: Brief summary (Goal, Changed files, Observed proof, Residual risk).
3. **Sign-off**: Include Co-Authored-By and session URL.
4. **Create**: `git commit -m "..."` (not amend unless explicitly requested).

## Push workflow

1. **Branch ancestry**: Confirm current branch is ahead of main.
2. **Rebase check**: No rebase -i or destructive reset needed.
3. **Push**: `git push origin <branch> -u`.
4. **No force**: Never use `--force` without explicit user instruction.

## Branch deletion

- **Never** delete a branch without user authorization and ancestry proof.
- Require explicit confirmation: "delete branch <name>".
- Verify the branch is merged into main or the deletion target.

## Report format

Use `.claude/scripts/handoff` to print the compact six-field report (Status,
Branch, Diff, QA, Next, Risk) — this is the exact format CLAUDE.md's
"Completion report" section mandates.

## Do not do

- Stage with `.` or `-A`
- Commit without explicit request
- Skip staged-check
- Delete branches without authorization
- Push without remote HEAD verification
- Stage specs without DJ_DIGGER_ALLOW_SPEC_STAGE
