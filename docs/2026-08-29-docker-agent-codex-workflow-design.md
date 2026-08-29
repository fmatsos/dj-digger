# Docker Agent + Codex Development Workflow Design

**Date:** 2026-08-29

## Goal

Replace the current Codex-centric orchestration loop in DJ Digger with a Docker Agent orchestration layer that keeps Codex focused on bounded implementation work, reduces repeated exploration and context loading, makes QA deterministic, and produces measurable before/after evidence on token and interaction cost.

## Current constraints

- DJ Digger remains a local-first Python 3.12 CLI.
- Existing `AGENTS.md`, scoped `AGENTS.md`, `.codex/scripts/*`, `.codex/skills/*`, CodeGraph integration, risk-based QA, privacy guards, and delivery rules are retained unless a later measured simplification proves them redundant.
- Codex must remain usable directly as a fallback; Docker Agent adoption must not make the repository dependent on Docker Agent for ordinary development.
- No automatic commit, push, reset, clean, stash, delete, or modification of protected local/private paths.
- Source music, local paths, library metadata, prompts, model responses, and command output from private sessions must never be copied into benchmark artifacts.

## Target architecture

```text
User
  |
  v
Docker Agent lead
  |-- classify/scope/route
  |-- use CodeGraph only when ownership is unknown
  |-- construct bounded task brief
  |
  +--> Codex harness worker
  |      |-- focused RED/GREEN implementation
  |      |-- scoped AGENTS.md / skills only
  |      `-- compact handoff
  |
  +--> deterministic QA gate
  |      changed-files -> qa-select -> qa-run
  |
  `--> risk reviewer only when required
         readonly, fresh context, compact verdict
```

Docker Agent owns orchestration. Codex owns coding loops. Deterministic scripts own classification that can be derived without a model.

## Agent set

### `lead`

Purpose: classify requests, identify ownership, delegate bounded work, run the deterministic gate, decide whether independent review is required, and aggregate the final report.

Initial model: a low-cost OpenAI model such as `gpt-5-mini`.

The lead is intentionally constrained:
- no source edits;
- small history;
- bounded tool output;
- low iteration count;
- CodeGraph/exploration only when file ownership is unknown;
- no automatic Git delivery.

### `codex-worker`

Docker Agent harness:

```yaml
harness:
  type: codex
```

No model override in V1. Codex keeps the user's normal CLI authentication/subscription and configured default model.

It receives only:
- Goal
- Owned files / subsystem
- Observable acceptance
- Relevant scoped instructions
- Required implementation skill
- Focused RED/GREEN test command
- Do-not-touch scope
- Expected return format

It must not repeat global exploration once the brief establishes ownership.

### `reviewer`

Fresh read-only review context. Invoked only for elevated-risk work:
- catalog schema/migrations;
- analysis worker/process boundaries;
- concurrency;
- public export/schema contracts;
- public CLI contract;
- privacy/security;
- cross-layer changes;
- explicit lead escalation after ambiguous QA/rework.

It reviews the final diff and relevant invariants, not the complete development history.

## Task sizing / routing

- **S** — docs, local fix, simple CLI/config change: `lead -> codex-worker -> QA`
- **M** — bounded multi-file or single-subsystem feature: `lead -> codex-worker -> QA -> conditional review`
- **L** — migration, DSP/process work, concurrency, cross-layer/public contract: `lead -> plan-only Codex when needed -> bounded Codex tasks -> QA -> reviewer`

The number of agents is not a quality metric. Specialties such as SQLite, native analysis, runtime proof, and Git delivery remain Codex skills rather than permanent agents.

## Deterministic QA

Existing project scripts stay authoritative:

```text
.codex/scripts/changed-files
  -> .codex/scripts/qa-select
  -> .codex/scripts/qa-run <profile>
```

A Docker-Agent-facing wrapper returns a compact machine-readable status. Passing QA must not trigger another model analysis. Failing QA returns only a bounded diagnostic to Codex.

## Context policy

Persistent prompt content is limited to orchestration rules and permanent invariants.

Repository context is loaded progressively:
1. root orchestration contract;
2. nearest scoped `AGENTS.md` after ownership is known;
3. architecture/spec/plan only when required by the task;
4. no repeated broad repository exploration after scope is established.

Suggested initial Docker Agent limits:
- lead: `max_iterations: 8`
- lead: `max_tool_result_tokens: 1500`
- lead: `max_old_tool_call_tokens: 4000`
- lead: `num_history_items: 8`
- lead: `compaction_threshold: 0.70`
- reviewer: similarly bounded, with a slightly larger tool-result allowance if diff review needs it.

Exact limits are calibration values and may only be changed after benchmark evidence.

## Budget policy

Use a named shared Docker Agent coordination budget for lead + reviewer. This prevents the orchestration layer from hiding cost shifted away from Codex.

Do not treat a configured maximum budget as actual usage. Actual Docker Agent usage is reported separately only when the installed Docker Agent version exposes a reliable usage measure. Otherwise report the overhead as unavailable and retain the configured budget as a ceiling.

## Permissions / privacy

- `redact_secrets: true`.
- filesystem access limited to repository paths needed by the role.
- protected paths remain blocked by existing `protect-local` policy.
- deny destructive shell/Git commands.
- ask before commit/push.
- no raw prompt/response/command-output retention in benchmark exports.
- benchmark session IDs are hashed before export.
- absolute paths are never emitted.

## Benchmark design

The benchmark is deterministic and independent from LLM interpretation.

### Source

Codex local state:
- `$CODEX_HOME`, defaulting to `~/.codex`;
- active rollouts under `sessions/`;
- archived rollouts optionally under `archived_sessions/`;
- JSONL rollouts are the durable history;
- SQLite may be used as an index when available but must not be the only source.

### Session identity

A Codex `session_id` is shared by the root thread and its sub-agents. The benchmark groups all threads sharing that ID.

Select the latest X **root sessions** whose canonical `cwd` is the DJ Digger repository or a descendant. Sort by persisted session timestamp, not filesystem mtime. Then include all child threads belonging to each selected session.

### Token accounting

For each thread, Codex token events contain accumulated totals. The collector must:
1. keep the latest valid cumulative total for the thread;
2. never sum cumulative token events within one thread;
3. aggregate the final totals of root + child threads.

Fields:
- total tokens;
- input tokens;
- cached input tokens;
- cache-write input tokens where available;
- output tokens;
- reasoning output tokens;
- cache-hit ratio.

Schema-version differences are handled with explicit parser adapters. Unknown events are ignored but counted toward a parse-coverage metric.

### Other directly observable metrics

Per session:
- elapsed duration from persisted timestamps;
- root user-turn count / interaction round-trips;
- root and child thread counts;
- tool-call counts by class;
- shell-command count;
- file-change events;
- CodeGraph/discovery command count;
- compaction count;
- approval count;
- sub-agent count;
- root vs sub-agent token share;
- QA invocation count;
- QA profile counts (`focused`, `subsystem`, `catalog`, `analysis`, `exports`, `runtime`, `full`);
- QA pass/fail count from command completion status.

### Deterministic derived metrics

Rules are versioned and documented:
- discovery ratio = discovery-classified shell calls / shell calls;
- repair cycle = source edit(s) after a failed QA gate before a later passing gate;
- post-review rework cycle = source edit(s) after a review event before final acceptance;
- full-QA rate = full QA invocations / QA invocations;
- repeated-discovery count = repeated normalized discovery operations in one root session;
- first-edit-to-final-green duration when timestamps exist.

Do not invent semantic metrics that cannot be proven from events. Missing metrics are `null` plus a coverage flag.

### Privacy-safe outputs

Default output directory: `.agent-benchmarks/` (gitignored).

Artifacts:
- `baseline.json`
- optional `baseline.csv`
- `after.json`
- `comparison.json`

No raw session payloads are copied.

### Comparison

Primary apples-to-apples metric: Codex usage before vs Codex harness usage after.

Use distributions, not only averages:
- count;
- median;
- p75;
- min/max where useful.

Report percentage delta for:
- Codex total tokens/session;
- uncached input tokens/session;
- output + reasoning tokens/session;
- user round-trips/session;
- discovery calls/session;
- compactions/session;
- QA invocations/session;
- full-QA rate;
- repair cycles/session;
- sub-agent token share;
- duration/session.

Docker Agent coordination overhead is a separate measure and must never be hidden inside the Codex improvement figure.

## Success criteria

Initial targets are calibration goals, not hard release gates:
- at least 30% lower median Codex total tokens per comparable session;
- materially fewer root user round-trips;
- lower repeated exploration/discovery;
- no reduction in final QA success;
- no increase in repair/review cycles;
- Docker Agent coordination remains inside its explicit shared budget;
- direct Codex fallback continues to work.

After 10-20 real post-migration sessions, recalibrate limits and routing from evidence rather than intuition.
