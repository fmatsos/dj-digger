---
name: runtime-proof
description: Validate real composition, exits, state, and artifacts for public entry points
---

## Purpose

Checks real composition and observable state changes. Exercises the public entry point (CLI command) and validates the result against observable proof.

## Checks

1. **Composition**: Real imports, real function calls, no fakes or stubs.
2. **Entry point**: CLI command runs with expected flags and arguments.
3. **Exit code**: Command exits with expected status (0 for success, non-zero for errors).
4. **State change**: Files, database, or artifacts created/modified as expected.
5. **Artifact presence**: Output files exist and contain expected content.

## Observable proof format

```
Command: <public entry point> <args>
Exit: 0
State: <file or DB query showing changed state>
Artifact: <path/to/output/file>
```

## Limitations

- Network or cloud resources that are inaccessible are reported as unverified.
- Async operations with background workers require explicit state polling or timing.
- Concurrency edge cases may require repeated runs to trigger.

## Do not do

- Use fakes, stubs, or mock HTTP responses
- Skip exit-code verification
- Assume state changed without querying it
- Report async operations as passed without polling
