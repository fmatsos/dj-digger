# Scripts Scope Instructions

This scope covers acceptance and automation scripts in the `scripts/` directory.

## Source library protection

The read-only source library principle is enforced: scripts must not modify
the source library directly. Acceptance scripts operate on bounded temporary
copies or isolated test data. When a script must verify behavior against real
library data, it uses a copy or snapshot, never the original.

Private values (musician names, track titles, local paths, workspace details)
must never appear in script output, logs, or error messages.

## Python and reproducibility

Scripts are written in Python 3.12. All commands are reproducible and
deterministic. External dependencies are declared and available in the
project environment.

Output is structured and explicit. Scripts remain silent on success and report
only errors or status changes.

## Error classification

Errors reported by scripts are classified as:
- Application failure (exit code ≥1 from the application under test)
- Environment failure (missing tool, configuration, or resource)
- Network failure (unreachable service or timeout)
- Permission failure (access denied to a file or directory)
- External service failure (API error from a third party)

Scripts do not attempt to recover from unclassified errors.

## Bounded resources

Temporary artifacts and working directories are cleaned up when the script
completes. Scripts operate within configured resource limits and do not exhaust
disk, memory, or CPU indefinitely.
