# Codex Development Harness Design

**Date:** 2026-08-27  
**Status:** Approved design, pending implementation plan

## Purpose

Build a Codex-only development harness for DJ Digger that makes future changes more
reliable while substantially reducing repeated exploration, duplicated reviews, long
tool output, and unnecessary model usage.

The harness consists of a concise root `AGENTS.md`, directory-scoped `AGENTS.md` files,
on-demand project skills, deterministic scripts, and only those Codex hooks that are
confirmed to be supported by the installed runtime.

## Goals

- Keep the root `AGENTS.md` below 200 lines, with a target of 120–160 lines.
- Load detailed guidance only when its scope or workflow requires it.
- Route architecture, supervision, and global review to GPT-5.6 Sol low.
- Route implementation to GPT-5.6 Luna low or medium according to complexity.
- Prove behavior on observable and public execution paths.
- Select QA proportionally to the changed files and risk.
- Protect local configuration, exports, databases, sets, and private library details.
- Preserve unrelated worktree changes and require explicit Git delivery scope.
- Produce compact, reproducible reports instead of copying long logs into context.

## Non-goals

- Supporting Claude Code or another agent runtime in the first version.
- Replacing project documentation with agent instructions.
- Encoding architectural judgment in shell hooks.
- Running the full QA suite after every local edit.
- Automatically committing, pushing, cleaning, stashing, or deleting user files.
- Treating a design or historical plan as shipped application behavior.

## Design principles

1. The root instruction file is a router and contract, not a complete manual.
2. Scoped instructions contain only rules specific to their directory.
3. Conditional workflows live in skills and load on demand.
4. Deterministic checks live in scripts and remain silent on success.
5. Hooks enforce only facts that can be checked reliably.
6. One implementation agent is the default for a bounded vertical change.
7. A focused test is preferred during implementation; broader QA follows risk.
8. Unit tests with fakes do not alone prove production composition.
9. Local acceptance is reported only when the real supported path was executed.
10. Private music-library facts never enter committed harness files or agent reports.

## Target structure

```text
AGENTS.md
.codex/
├── skills/
│   ├── task/SKILL.md
│   ├── implement/SKILL.md
│   ├── qa/SKILL.md
│   ├── runtime-proof/SKILL.md
│   ├── sqlite-change/SKILL.md
│   ├── native-analysis/SKILL.md
│   └── ship/SKILL.md
├── hooks/
└── scripts/
    ├── project-env
    ├── changed-files
    ├── protect-local
    ├── qa-select
    ├── qa-run
    ├── runtime-smoke
    ├── package-check
    ├── staged-check
    └── handoff
src/dj_digger/AGENTS.md
src/dj_digger/catalog/AGENTS.md
src/dj_digger/analysis/AGENTS.md
src/dj_digger/exports/AGENTS.md
tests/AGENTS.md
scripts/AGENTS.md
skills/AGENTS.md
docs/AGENTS.md
```

The implementation may omit a proposed file when current Codex capabilities or the
repository show that it would duplicate another mechanism. It must not invent an
unsupported hook interface.

## Root instruction contract

The root `AGENTS.md` contains, in this order:

1. project purpose and a compact architecture map;
2. exploration order and stop conditions;
3. permanent safety and privacy invariants;
4. model and delegation policy;
5. observable-proof policy;
6. risk-based QA routing;
7. Git scope and delivery rules;
8. skill routing table;
9. compact completion report format.

It instructs agents to use CodeGraph first when `.codegraph/` exists, use one semantic
search when the correct symbol remains unknown, and stop exploring once the execution
path is established. It also requires consultation of the closest applicable scoped
`AGENTS.md` before editing files below that directory.

## Scoped instructions

### Python application scope

`src/dj_digger/AGENTS.md` defines Python 3.12, strict mypy, Ruff, focused modules,
observable failures, `WorkspaceApplication` as the catalog command composition
boundary, runtime resources through `importlib.resources`, and behavior-first tests.

### Catalog scope

`src/dj_digger/catalog/AGENTS.md` defines the SQLite V7 boundary: canonical facts,
append-only history, rebuildable projections, transactional mutations, atomic
migrations, foreign-key validation, concurrency coverage, and wheel independence
from the checkout.

### Analysis scope

`src/dj_digger/analysis/AGENTS.md` defines a fresh child per track, versioned and
bounded JSON IPC, the parent as the sole SQLite writer, bounded `float32` processing,
process-group cleanup, visible crash and timeout outcomes, and analyzer-identity
updates for behavior-changing DSP modifications.

### Export scope

`src/dj_digger/exports/AGENTS.md` defines consistent SQLite reads, schema validation
before publication, staging followed by atomic replacement, indivisible analysis
facets, and exact `(source_id, track_id, path)` identities.

### Tests scope

`tests/AGENTS.md` requires a relevant RED, assertions on output, exit status, state,
or artifacts, deterministic fixtures, focused tests during implementation, and
production-composition evidence for integration claims.

### Scripts scope

`scripts/AGENTS.md` prohibits writes to the source library and private values in logs.
Acceptance scripts use bounded temporary copies, Python 3.12, reproducible commands,
and explicitly distinguish application, environment, and network failures.

### Curation skill scope

`skills/AGENTS.md` preserves the existing curator boundary. It consumes the four
exports from one run, treats `tracks.tsv` as the availability authority, preserves
track identities, does not replace real exports with fixtures, and validates the
published set artifacts.

### Documentation scope

`docs/AGENTS.md` distinguishes current architecture, measured acceptance, designs,
and historical plans. It prohibits rewriting history to match implementation and
prevents staging `docs/superpowers/specs/**` without explicit authorization.

## Model and delegation policy

| Responsibility | Model | Effort |
| --- | --- | ---: |
| Architecture, supervision, arbitration | GPT-5.6 Sol | low |
| Global and final review | GPT-5.6 Sol | low |
| Simple bounded implementation | GPT-5.6 Luna | low |
| Complex multi-file implementation | GPT-5.6 Luna | medium |
| Independent targeted risk review | GPT-5.6 Luna | medium |

Sol may directly perform a trivial, fully understood change. Otherwise, Sol scopes
the task and sends one bounded implementation tranche to Luna. A second agent is used
only for a concrete risk such as a migration, concurrency, filesystem safety, native
process handling, or DSP correctness.

Every delegated implementation receives only:

```text
Goal:
Owned files:
Observable acceptance:
Relevant AGENTS.md:
Required skill:
Focused QA:
Do not touch:
Return:
```

The worker returns changed files, observed RED, observed GREEN, and residual risk.
Sol remains responsible for the final diff, public-path evidence, Git scope, and
`COMPLETE`, `PARTIAL`, or `BLOCKED` classification.

## Skills

### `task`

Produces a compact scope, observable outcome, risk level, likely files, proof, and
execution choice. It routes to specialized skills and prevents repeated exploration.

### `implement`

Runs the lightweight RED/GREEN loop: select observable proof, observe the expected
failure, implement the minimum robust change, obtain targeted GREEN, inspect the
diff, and report residual risk.

### `qa`

Provides `focused`, `subsystem`, `full`, and `real` profiles. Selection depends on
changed files and risk. Long logs stay outside the agent context; only the result and
actionable errors are returned.

### `runtime-proof`

Checks the public entry point, real dependency composition, nominal behavior, one
significant failure, exit status, and resulting SQLite state or artifacts. A fake on
the claimed integration path invalidates the proof.

### `sqlite-change`

Checks starting and target versions, rollback, foreign keys, preserved history,
projection rebuilds, reader/writer behavior, packaged SQL resources, and migration
failure atomicity.

### `native-analysis`

Requires Python 3.12 and the `analysis` extra, evidence-based OOM diagnosis, bounded
memory, fresh workers, bounded IPC, parent-only persistence, visible crash outcomes,
and honest reporting when a real library is unavailable.

### `ship`

Requires an explicit file list, protects local artifacts, checks the staged diff,
creates an atomic commit only when requested, verifies an explicitly requested push,
and deletes branches only after ancestry checks and authorization.

## Deterministic scripts and hooks

Scripts provide stable commands for environment setup, changed-file discovery, local
data protection, QA selection and execution, runtime smoke tests, packaging checks,
staged-diff validation, and compact handoffs.

Protected paths initially include:

```text
config/local.toml
workspace/**
sets/**
*.sqlite
*.sqlite-wal
*.sqlite-shm
docs/superpowers/specs/**
```

Specs require explicit staging authorization. Other protected local data requires an
explicitly scoped user instruction before modification or staging.

QA selection follows the changed files:

| Change | Minimum validation |
| --- | --- |
| Documentation only | diff check and objective document checks |
| Local Python module | focused pytest and Ruff |
| Production source | relevant mypy coverage |
| Catalog or SQL | catalog, migration, and packaging checks |
| Analysis worker | protocol, crash, timeout, and pipeline tests |
| Exports or schemas | export tests, fixtures, and schema validation |
| CLI | public command and exit-code tests |
| Cross-layer change | full QA profile |

A temporary QA record may cache the diff hash, profile, commands, result, and time.
It is reusable only for an identical diff and an equal or weaker requested profile.
Branch, diff, or relevant dependency changes invalidate it. A cached result never
substitutes for an unexecuted real acceptance run.

Codex-native hooks are used only after their current format and event semantics are
verified. Any unsupported event remains an explicit script call from a skill. Git
hooks remain distinct from Codex hooks.

## Error handling

- Script success is silent or one line.
- Script failure shows the failing command, relevant errors, and a temporary log path.
- Application, environment, network, permission, and external-service failures are
  classified separately.
- Hooks never clean, stash, reset, delete, commit, or push automatically.
- Missing authority yields `BLOCKED`, not an inferred permission.
- Inaccessible real-library evidence is reported as unverified, never as passed.

## Completion report

Every workflow converges on:

```text
Status : COMPLETE | PARTIAL | BLOCKED
Change : <brief summary>
Proof  : <observable command or path>
QA     : <profiles actually executed>
Git    : <worktree state or commit>
Risk   : <none or precise reservation>
```

## Verification strategy

Implementation verification includes:

- root `AGENTS.md` below 200 lines;
- valid placement and non-duplicated scoped instructions;
- valid skill frontmatter and complete skill routing;
- executable, syntax-checked scripts;
- valid Codex configuration;
- no committed private path or track information;
- dry-run protection checks in a temporary repository;
- QA selection scenarios for docs, Python, catalog, analysis, exports, and CLI;
- QA cache reuse and invalidation scenarios;
- simulated model selection for Luna low, Luna medium, and Sol low;
- `git diff --check` and preservation of pre-existing local files.

## Implementation sequence

1. Confirm installed Codex support and inventory existing harness files.
2. Create the root `AGENTS.md`.
3. Create only the justified scoped `AGENTS.md` files.
4. Implement and test deterministic scripts.
5. Implement the seven project skills.
6. Connect only supported Codex hooks.
7. Run structural, routing, protection, and QA-selection tests.
8. Audit duplication and instruction line counts.
9. Perform the global Sol low review.
10. Present the complete diff without committing or pushing automatically.

## Acceptance criteria

The harness is accepted when it retains all critical project invariants while
reducing default instruction volume, selects models and QA deterministically, proves
integration through public behavior, protects local data, produces compact reports,
and passes its dry-run scenarios without modifying the user's existing local files.
