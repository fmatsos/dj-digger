# Application Layer Instructions

This scope covers Python 3.12 application code, CLI entry points, and command composition.

Canonical implementation is split between `src/dj_digger/core/` (framework-free
use cases, catalog, workers, and resources) and `src/dj_digger/cli/` (Typer,
Rich, terminal rendering, completion, and process launching). There are no
top-level compatibility modules outside those packages.

## Python and type safety

All Python code in this layer must pass:
- `python -m mypy` with strict mode for this directory
- `python -m ruff check` with the project configuration
- Format verification with `ruff format --check`

No warnings, hints, or deferred types are permitted.

## Modules and composition

Code is organized into focused, single-responsibility modules.
The `CoreApplication` class is the catalog command composition boundary
for runtime resource loading and session lifecycle. Initialization errors in
`CoreApplication` are fatal and must be caught and reported at the CLI level.

All runtime resources (templates, schema, data files) load through
`importlib.resources` to remain independent of the checkout directory.

## Observable failures

Errors that cannot be recovered must produce:
- A clear, actionable message at the CLI
- An exit code ≥1
- Logged evidence of the failure point and state

Unhandled exceptions are forbidden. Catch and classify exceptions at layer
boundaries.

## Tests for this scope

Behavior-first tests document and assert the public API contract.
Implementation details of individual functions are tested when they affect
observable behavior. Fixtures are deterministic and local.
