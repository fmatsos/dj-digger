# DJ Digger Agent Contract

## Mission and architecture

DJ Digger is a music library analysis system that ingests track metadata, runs
analysis workers, maintains a SQLite V9 catalog, and exports structured data.
The public entry point is the CLI application. Docker Agent may orchestrate
bounded work while Codex remains the implementation worker; direct Codex use
continues as the fallback. Changes stay vertically scoped from CLI flags through catalog mutations to worker
concurrency and export publication. The system spans application code, catalog
schema, analysis workers, exports, and integration tests. Each layer has its own
invariants and acceptance criteria.

Architecture, supervision, arbitration, and independent risk review are routed
to GPT-5.6 Sol medium. Simple bounded implementation is routed to GPT-5.6 Luna
low, while complex multi-file implementation uses GPT-5.6 Luna medium. Under
Docker Agent, the Luna-low lead owns orchestration, delegates bounded work to
the Luna-medium Codex worker, and uses the Sol-medium reviewer for elevated-risk
changes. CodeGraph is an optional accelerator: use it first when available, but
fall back to Read/Grep/rg without blocking when it is absent.

## Instruction scope

This file applies to all work on the repository. Scoped `AGENTS.md` files below
each major directory define rules specific to their scope. Source code changes
require consultation of the closest scoped file before editing: check
`src/dj_digger/AGENTS.md` before editing application code, `src/dj_digger/catalog/AGENTS.md`
for schema or migrations, `tests/AGENTS.md` for test changes, and `docs/AGENTS.md`
for documentation changes. No edit to code below a scoped directory may proceed
without reading that directory's closest `AGENTS.md` first.

## Exploration order

1. Check if `.codegraph/` exists; use CodeGraph with semantic queries first when
   the code location is unknown and the command is available.
2. Perform one semantic search if the execution path or symbol location remains
   unknown after CodeGraph fails or is unavailable; ordinary `rg` is sufficient
   when the repository has no CodeGraph index.
3. Read directly once the execution path is established and the change scope is
   clear.
4. Stop exploring when ownership and file boundaries are defined. Avoid repeated
   re-reads of the same areas or exploration after the path is clear.

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
| Architecture, supervision, arbitration | GPT-5.6 Sol | medium |
| Global and final review | GPT-5.6 Sol | medium |
| Lightweight orchestration / simple bounded implementation | GPT-5.6 Luna | low |
| Complex multi-file implementation | GPT-5.6 Luna | medium |
| Independent targeted risk review | GPT-5.6 Sol | medium |

Sol scopes tasks and routes bounded, self-contained tranches to Luna. Delegated
work receives: Goal, Owned files, Observable acceptance, Relevant AGENTS.md,
Required skill, Focused QA, Do not touch, Return. Luna reports observed RED,
GREEN, and residual risk. Sol owns final diff review, public-path proof,
Git scope, and completion status.

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

Sol remains responsible for staged diff checks and explicit commit scope. The
worktree state is preserved; multi-task branches are not automatically squashed or
rebased. Commits include bounded worker briefs (Goal, Changed files, Observed
proof, Residual risk) in the message. Each workflow converges on a structured
completion report. Git scope is explicit; delivery must be requested separately.

## Skill routing

Skills route lightweight workflows: `task` scopes and prevents re-exploration;
`implement` runs RED/GREEN loops; `qa` executes selection-based validation;
`runtime-proof` validates public entry points; `sqlite-change` handles migrations;
`native-analysis` provides analysis evidence; `commit` creates a scoped local
commit; `mr` creates or updates a GitHub pull request; `ship` orchestrates QA,
commits, push, and pull-request checks for explicitly authorized end-to-end
delivery. Deterministic scripts provide environment setup, file discovery, local
data protection, QA selection, and compact handoffs. All scripts
remain silent on success and report only errors or status changes.

## Orchestration modes

- Under a Docker Agent bounded brief, Codex implements only the stated owned
  files and acceptance criteria, then returns its compact handoff. It does not
  re-orchestrate or repeat broad exploration after ownership is established.
- When invoked directly, Codex retains the routing, scoped-instruction, QA,
  and delivery workflow below. Docker Agent is optional and never a prerequisite.
- The external deterministic QA gate owns final profile selection. Focused
  implementation checks remain with the worker; a passing gate is not reinterpreted.

## Completion report

Every workflow ends with a structured report using `.agents/scripts/handoff`'s
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
