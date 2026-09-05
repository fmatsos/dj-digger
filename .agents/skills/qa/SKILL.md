---
name: qa
description: Execute risk-based QA profiles; select by changed files and report results
---

## Purpose

Selects and runs risk-based validation profiles for direct Codex work.
Changed files determine QA scope (docs, focused, subsystem, catalog, analysis,
exports, runtime, full). Under Docker Agent, focused implementation checks remain
with the worker and `.docker-agent/scripts/qa-gate` owns final external QA.

## Profiles

- **docs**: Diff checks and objective document review
- **focused**: Local Python module changes, pytest, Ruff validation
- **subsystem**: Production source changes, mypy coverage
- **catalog**: Catalog consistency, migration, packaging checks
- **analysis**: Protocol, crash, timeout tests for workers
- **exports**: Export tests and schema validation
- **runtime**: CLI commands and exit-code tests
- **full**: Cross-layer changes, all profiles executed

## Usage

```sh
.agents/scripts/qa-select < changed-files.txt > profile.txt
.agents/scripts/qa-run "$(cat profile.txt)" -- test-command
```

## Workflow

1. **Select**: Run `.agents/scripts/qa-select` on stdin (one file path per line).
2. **Run**: Execute `.agents/scripts/qa-run <profile> -- <test-command>`.
3. **Report**: Output indicates PASS or FAIL with profile name.
4. **Assess**: If FAIL, report specific test failure and residual risk.

The final gate emits machine-readable pass/fail evidence. Do not ask a model to
reinterpret a passing gate; investigate only a failure or missing evidence.

## Do not do

- Skip QA profile selection based on risk assessment
- Run untested profile combinations
- Ignore real library access limits
- Report inaccessible libraries as passed
