# DJ Digger Agent Contract

## Mission and architecture

DJ Digger is a music library analysis system that ingests track metadata, runs
analysis workers, maintains a SQLite V7 catalog, and exports structured data.
The public entry point is the CLI application. Claude Code orchestrates bounded,
vertically scoped changes: from CLI flags through catalog mutations to worker
concurrency and export publication. The system spans application code, catalog
schema, analysis workers, exports, and integration tests. Each layer has its own
invariants and acceptance criteria.

Architecture, supervision, and final review are routed to Sonnet (medium effort).
Simple, bounded implementation is routed to Haiku. Complex multi-file changes or
independent risk review are routed to Sonnet (low effort, when available).
CodeGraph indexes all symbols and enables semantic searches. New work always
checks CodeGraph first.

## Instruction scope

This file applies to all work on the repository. Scoped `CLAUDE.md` files below
each major directory define rules specific to their scope. Source code changes
require consultation of the closest scoped file before editing: check
`src/dj_digger/CLAUDE.md` before editing application code,
`src/dj_digger/catalog/CLAUDE.md` for schema or migrations,
`src/dj_digger/analysis/CLAUDE.md` for analysis worker changes,
`src/dj_digger/exports/CLAUDE.md` for export or schema changes,
`tests/CLAUDE.md` for test changes, `docs/CLAUDE.md` for documentation changes,
`scripts/CLAUDE.md` for acceptance and automation scripts, and `skills/CLAUDE.md`
for curator workflow and set management skills. No edit to code below a scoped
directory may proceed without reading that directory's closest `CLAUDE.md` first.

## Exploration order

1. Check if `.codegraph/` exists; use CodeGraph with semantic queries first when
   the code location is unknown.
2. Perform one semantic search if the execution path or symbol location remains
   unknown after CodeGraph fails or is unavailable.
3. Read directly once the execution path is established and the change scope is
   clear.
4. Stop exploring when ownership and file boundaries are defined. Avoid repeated
   re-reads of the same areas or exploration after the path is clear.
5. The `pyright-lsp` plugin (enabled via `.claude/settings.json`) provides live
   Python type/definition/reference queries through the `LSP` tool — check it
   before falling back to CodeGraph or grep for symbol-level Python questions.

## Permanent invariants

- Private library facts (musician names, track titles, local paths) must never
  appear in committed files, logs, agent reports, or staged diffs.
- Protected paths (`config/local.toml`, `workspace/`, `sets/`, `*.sqlite*`,
  `.specifications/**`) require explicit scoped authorization before any
  modification or staging.
- No automatic commits, pushes, file deletes, stash operations, or resets without
  explicit and specific user instructions.
- All executable changes are verified with observable, reproducible, and public-path
  proofs before merging.
- Preserve unrelated worktree changes and require explicit Git delivery scope.

## Models and delegation

| Work | Model | Effort |
| --- | --- | --- |
| Architecture, supervision, arbitration | Sonnet | medium |
| Global and final review | Sonnet | medium |
| Research and simple bounded implementation | Haiku | — |
| Complex multi-file implementation | Sonnet | low (when available) |
| Independent targeted risk review | Sonnet | low (when available) |

Sonnet (medium effort) scopes tasks and routes bounded, self-contained tranches
to Haiku or Sonnet (low effort). Delegated work receives: Goal, Owned files,
Observable acceptance, Relevant CLAUDE.md, Required skill, Focused QA, Do not
touch, Return. The delegate reports observed RED, GREEN, and residual risk.
Sonnet (medium effort) owns final diff review, public-path proof, Git scope,
and completion status.

## Observable proof

Every change is reported with observable proof of execution: the command run, its
output, the resulting state (exit status, files modified, database state), or
artifact presence. Nominal behavior requires testing the entry point. A significant
failure or boundary condition is tested when risk is elevated. Fakes on the claimed
integration path invalidate the proof. Inaccessible real libraries are reported as
unverified, never as passed.

## Risk-based QA

QA profiles (docs, focused, subsystem, catalog, analysis, exports, runtime, full) are
selected by the set of changed files and residual risk. Documentation changes require diff checks and objective
document review. Local Python module changes require focused pytest and Ruff
validation. Production source changes require mypy coverage. Catalog or SQL
changes require catalog consistency, migration, and packaging checks. Analysis
worker changes require protocol, crash, and timeout tests. Export or schema
changes require export tests and schema validation. CLI changes require public
command and exit-code tests. Cross-layer changes require the full QA profile.

## Git and privacy

Sonnet (medium effort) remains responsible for staged diff checks and explicit
commit scope. The worktree state is preserved; multi-task branches are not
automatically squashed or rebased. Commits include bounded worker briefs (Goal,
Changed files, Observed proof, Residual risk) in the message. Each workflow
converges on a structured completion report. Git scope is explicit; delivery
must be requested separately.

## Skill routing

Skills route lightweight workflows: `task` (`.claude/skills/task/SKILL.md`)
scopes and prevents re-exploration; `implement` (`.claude/skills/implement/SKILL.md`)
runs RED/GREEN loops; `qa` (`.claude/skills/qa/SKILL.md`) executes
selection-based validation; `runtime-proof` (`.claude/skills/runtime-proof/SKILL.md`)
validates public entry points; `sqlite-change` (`.claude/skills/sqlite-change/SKILL.md`)
handles migrations; `native-analysis` (`.claude/skills/native-analysis/SKILL.md`)
provides analysis evidence; `ship` (`.claude/skills/ship/SKILL.md`) handles staged
diffs and commits. These skills are invoked as Claude Code slash commands
(`/task`, `/implement`, `/qa`, `/runtime-proof`, `/sqlite-change`,
`/native-analysis`, `/ship`). Deterministic scripts under `.claude/scripts/`
provide environment setup, file discovery, local data protection, QA selection,
and compact handoffs. All scripts remain silent on success and report only
errors or status changes.

## Completion report

Every workflow ends with a structured report using `.claude/scripts/handoff`'s
six fields:

```
Status : COMPLETE | PARTIAL | BLOCKED
Branch : <current branch>
Diff   : <compact changed-file summary>
QA     : <profiles actually executed>
Next   : <follow-up action or none>
Risk   : <none or precise reservation>
```

Status values: COMPLETE when the task is done and verified; PARTIAL when some
work is done but dependencies or prerequisites block completion; BLOCKED when
no progress can be made without additional information or explicit authorization.
Reports are compact and reproducible, avoiding long logs in context.
