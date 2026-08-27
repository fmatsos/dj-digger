---
name: implement
description: Run the observable RED/GREEN TDD loop; verify changes before handoff
---

## Purpose

Executes the test-driven implementation loop. Verifies every change is observable, reproducible, and public-path only. Fakes on the claimed integration path invalidate the proof.

## Steps

1. **Understand**: Read the task brief and scoped CLAUDE.md.
2. **Plan**: Identify entry points, owned files, and dependencies.
3. **RED**: Run test suite; confirm the test fails as expected.
4. **Code**: Edit files to satisfy the test.
5. **GREEN**: Run test suite; confirm the test passes.
6. **Verify**: Confirm the change is observable:
   - No fakes or stubs in the implementation path
   - All real library calls are tested or marked unverified
   - Exit codes, file state, or database state changed as expected
7. **Report**: Observed RED command/output, GREEN command/output, residual risk.

## Observable proof

- Command run (exact sh invocation)
- Exit status (0 or non-zero)
- Files modified (git status, diff)
- Database state (sqlite3 query output, pragma foreign_keys check)
- Artifact presence (file path exists and contains expected content)

## Limitations

Inaccessible real libraries (network, cloud, third-party) are reported as unverified, not passed.

## Do not do

- Use fakes, stubs, or mock patches on the implementation path
- Commit without explicit handoff
- Skip the GREEN step
- Ignore residual risk or boundary conditions
