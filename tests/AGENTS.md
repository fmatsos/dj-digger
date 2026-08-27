# Test Scope Instructions

This scope covers test structure, fixtures, and acceptance criteria.

## Relevant RED

Every test file documents a relevant failure case first. Tests are written
to make that failure observable and reproducible. The observable RED shows
the assertion, state, or exit code that the test will verify.

Relevant means: the test failure directly reflects the feature being tested or
a boundary condition that affects correctness.

## Assertions

Tests assert on:
- Command output and format
- Exit codes and error messages
- Resulting state (files, database, directory structure)
- Artifact presence or absence
- Determinism and idempotence

Assertions focus on behavior, not internal implementation details.

## Deterministic fixtures

Fixtures are local and do not depend on external services or network.
Fixtures are deterministic: the same fixture setup produces the same state
every time. Randomized or time-dependent fixtures are avoided.

Fixtures are minimal and isolated. A test cleans up its own artifacts when
complete.

## Public composition verification

observable RED, public composition: Integration tests that claim to verify
end-to-end behavior must execute the public composition: the real CLI entry
point, real dependency injection, real module imports. Fakes on any part of
the claimed path invalidate the test.

If a real dependency is unavailable (e.g., a music library), the test is marked
as unverified and does not claim to pass.

## Focused tests during implementation

During implementation, focus tests are run first. Broader test suites are run
when the change is complete and risk is low.
