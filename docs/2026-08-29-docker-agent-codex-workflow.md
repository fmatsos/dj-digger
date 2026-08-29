# Docker Agent + Codex Development Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce Docker Agent as DJ Digger's orchestration layer, keep Codex as a bounded coding harness, move QA/routing work to deterministic scripts where possible, and measure the resulting token/interaction reduction with a reproducible Codex-session benchmark.

**Architecture:** Docker Agent provides a small `lead -> codex-worker -> optional reviewer` workflow. Existing DJ Digger scripts remain authoritative for changed-file classification, QA, privacy, and Git safety. A standard-library Python benchmark parses recent Codex rollout JSONL, groups root/sub-agent threads by session ID, and produces privacy-safe before/after metrics.

**Tech Stack:** Docker Agent, Codex CLI, Python 3.12 standard library, POSIX shell, JSON/JSON Schema, existing `pytest`, Ruff, mypy, CodeGraph, Git.

**Spec:** `docs/superpowers/specs/2026-08-29-docker-agent-codex-workflow-design.md`

## Global Constraints

- Docker Agent orchestrates; Codex implements bounded work.
- Direct Codex usage remains supported as a fallback.
- Do not delete existing `.codex` skills/scripts in V1.
- No automatic commit, push, reset, clean, stash, delete, or protected-path mutation.
- Preserve existing `protect-local`, staged checks, scoped `AGENTS.md`, CodeGraph-first exploration rule, and six-line handoff.
- Benchmark collection is deterministic and never uses an LLM.
- Benchmark outputs never contain raw prompts, responses, command output, library facts, absolute paths, or unhashed session IDs.
- Token events are cumulative: keep the latest per thread, then sum root + child thread totals.
- Docker Agent overhead is reported separately from Codex usage.
- Generated benchmark data lives under `.agent-benchmarks/` and is gitignored.
- New Docker Agent/harness files are classified as `focused` QA unless they also modify a production subsystem.

---

## File map

Create:

```text
docker-agent.yaml
.docker-agent/
  README.md
  instructions/
    lead.md
    reviewer.md
  schemas/
    task-brief.schema.json
    review-result.schema.json
    benchmark.schema.json
  scripts/
    codex-session-benchmark
    benchmark-compare
    qa-gate
    session-guard
tests/
  fixtures/codex_sessions/
    legacy-root.jsonl
    paginated-root.jsonl
    root-with-subagent.jsonl
    qa-repair-cycle.jsonl
    malformed-and-unknown.jsonl
  test_agent_benchmark.py
  test_agent_benchmark_compare.py
```

Modify:

```text
.gitignore
AGENTS.md
.codex/scripts/qa-select
.codex/skills/task/SKILL.md
.codex/skills/qa/SKILL.md
.codex/tests/test-harness.sh
docs/README.md (or the existing agent-development documentation index)
```

Do not create production package dependencies for this workflow.

---

### Task 1: Build the deterministic Codex session benchmark collector

**Files:**
- Create: `.docker-agent/scripts/codex-session-benchmark`
- Create: `.docker-agent/schemas/benchmark.schema.json`
- Create: `tests/fixtures/codex_sessions/*.jsonl`
- Create: `tests/test_agent_benchmark.py`
- Modify: `.gitignore`

**Interfaces:**
- CLI:
  ```text
  .docker-agent/scripts/codex-session-benchmark
      --repo PATH
      --limit N
      [--codex-home PATH]
      [--include-archived]
      --output FILE
      [--csv FILE]
  ```
- Input: Codex rollout JSONL under `$CODEX_HOME/sessions` and optional `archived_sessions`.
- Output: schema-versioned JSON plus optional flat CSV summary.

- [ ] **Step 1: Add privacy-safe synthetic fixtures**

Fixtures must contain only invented paths such as `/repo/dj-digger`, synthetic commands, synthetic IDs, and synthetic token counts. Include:
- one legacy-history root session;
- one paginated-history root session;
- one session with two child/sub-agent threads sharing the same `session_id`;
- one failed-QA -> edit -> passing-QA sequence;
- unknown/malformed non-critical events.

No fixture may be copied from a real user session.

- [ ] **Step 2: Write failing session-selection tests**

Test that the collector:
- resolves `CODEX_HOME`, defaulting to `~/.codex`;
- selects only sessions whose persisted `cwd` is the repo or a descendant;
- groups files by `session_id`;
- selects the latest X root sessions by persisted timestamp;
- includes every child thread in selected session groups;
- does not use file mtime for ordering.

Example assertion:

```python
assert report["summary"]["session_count"] == 2
assert report["sessions"][0]["thread_count"] == 3
assert "cwd" not in report["sessions"][0]
assert "session_id" not in report["sessions"][0]
assert report["sessions"][0]["session_key"].startswith("sha256:")
```

- [ ] **Step 3: Run RED**

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache \
uv run --python 3.12 --with pytest \
pytest tests/test_agent_benchmark.py -q
```

Expected: FAIL because the collector does not exist.

- [ ] **Step 4: Implement streaming JSONL discovery/parsing**

Use only Python standard library:
- `argparse`
- `json`
- `pathlib`
- `hashlib`
- `datetime`
- `statistics`
- `csv`

Read JSONL line-by-line. Never load an entire rollout solely to find metadata. Unknown event types increment `unknown_event_count` and are otherwise ignored.

Canonicalize the requested repository path before matching persisted `cwd`.

- [ ] **Step 5: Implement version-tolerant root/sub-agent grouping**

Normalize metadata into an internal record:

```python
@dataclass(frozen=True)
class ThreadMeta:
    session_id: str
    thread_id: str
    parent_thread_id: str | None
    cwd: Path | None
    started_at: datetime
    history_mode: str | None
```

When legacy metadata lacks a parent field, group by `session_id` and treat the earliest non-child-looking thread as root only if exactly one deterministic candidate exists. Otherwise mark root detection coverage incomplete rather than guessing.

- [ ] **Step 6: Implement correct cumulative token accounting**

Normalize the latest per-thread cumulative usage:

```python
@dataclass(frozen=True)
class TokenUsage:
    total_tokens: int
    input_tokens: int
    cached_input_tokens: int
    cache_write_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
```

For each thread:
- replace the previous usage snapshot when a later valid cumulative snapshot appears;
- never add cumulative events to each other;
- at session aggregation time, add final thread totals once.

Test with three cumulative token events in one thread and assert only the last is used.

- [ ] **Step 7: Implement directly observable event metrics**

Count:
- root user turns;
- total/root/child threads;
- command executions;
- file-change events;
- MCP/tool calls;
- CodeGraph/discovery commands;
- compactions;
- approvals;
- sub-agent activity;
- QA gate invocations and profiles;
- command exit status for QA pass/fail.

Normalize shell commands to categories; do not emit raw command strings.

Discovery classifier V1 recognizes command basename/prefixes:
`rg`, `grep`, `git grep`, `find`, `fd`, `ls`, `tree`, `sed`, `cat`, `head`, `tail`, `codegraph`, and read-only `git status|diff|log|show`.

QA classifier recognizes:
`.codex/scripts/qa-run`, `.docker-agent/scripts/qa-gate`, `pytest`, `ruff`, `mypy`, `package-check`, `git diff --check`, and `.codex/tests/test-harness.sh`.

- [ ] **Step 8: Implement deterministic derived metrics**

Use event order/timestamps only:
- `discovery_ratio`;
- `repeated_discovery_count`;
- `qa_repair_cycles`;
- `post_review_rework_cycles`;
- `full_qa_rate`;
- `first_edit_to_final_green_seconds`;
- `subagent_token_share`.

If required evidence is absent, emit `null`, never a guessed value.

- [ ] **Step 9: Add parse coverage**

Per report/session expose coverage such as:

```json
{
  "coverage": {
    "metadata": 1.0,
    "token_usage": 0.9,
    "timestamps": 1.0,
    "root_detection": 1.0
  },
  "unknown_event_count": 4
}
```

A new Codex schema must therefore degrade transparently instead of silently corrupting the benchmark.

- [ ] **Step 10: Validate output against `benchmark.schema.json` in tests**

The runtime collector itself should not add a `jsonschema` dependency. Tests may use the project's existing `jsonschema` dependency.

- [ ] **Step 11: Add `.agent-benchmarks/` to `.gitignore`**

Also refuse an output path inside source-library/protected paths when the collector is run from DJ Digger.

- [ ] **Step 12: Run GREEN and static checks**

```bash
UV_CACHE_DIR=/tmp/dj-digger-uv-cache \
uv run pytest tests/test_agent_benchmark.py -q

UV_CACHE_DIR=/tmp/dj-digger-uv-cache \
uv run ruff check .docker-agent/scripts/codex-session-benchmark tests/test_agent_benchmark.py
```

- [ ] **Step 13: Commit if explicitly authorized**

Suggested subject:

```text
feat(dev): add deterministic Codex session benchmark
```

---

### Task 2: Build deterministic baseline comparison

**Files:**
- Create: `.docker-agent/scripts/benchmark-compare`
- Create: `tests/test_agent_benchmark_compare.py`

**Interfaces:**

```text
.docker-agent/scripts/benchmark-compare
    BASELINE.json AFTER.json
    --output COMPARISON.json
```

- [ ] **Step 1: Write failing comparison tests**

For every numeric metric with enough coverage, assert:
- count;
- median;
- p75;
- percentage delta.

Do not use means as the primary comparison.

- [ ] **Step 2: Implement percentile calculation deterministically**

Document one interpolation rule and test odd/even/small sample sizes.

- [ ] **Step 3: Compare at least**

```text
tokens.total
tokens.input
tokens.uncached_input
tokens.output
tokens.reasoning_output
root_user_turns
discovery_calls
repeated_discovery_count
compactions
qa_invocations
full_qa_rate
qa_repair_cycles
post_review_rework_cycles
subagent_token_share
duration_seconds
```

- [ ] **Step 4: Keep Docker Agent overhead separate**

Comparison output contains:

```json
{
  "codex": { "...": "before/after deltas" },
  "docker_agent_overhead": {
    "token_usage": null,
    "budget_ceiling_tokens": 20000,
    "measurement_status": "unavailable|measured"
  }
}
```

Never infer actual usage from the budget ceiling.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_agent_benchmark_compare.py -q
uv run ruff check .docker-agent/scripts/benchmark-compare tests/test_agent_benchmark_compare.py
```

---

### Task 3: Capture and freeze the pre-Docker-Agent baseline

**Files generated only:**
- `.agent-benchmarks/baseline-YYYYMMDD.json`
- optional `.agent-benchmarks/baseline-YYYYMMDD.csv`

No repository source modification.

- [ ] **Step 1: Run the collector before orchestration changes**

Recommended starting sample: 20 recent DJ Digger root sessions, configurable if fewer/more representative sessions exist.

```bash
.docker-agent/scripts/codex-session-benchmark \
  --repo . \
  --limit 20 \
  --output .agent-benchmarks/baseline-20260829.json \
  --csv .agent-benchmarks/baseline-20260829.csv
```

- [ ] **Step 2: Inspect coverage, not content**

Reject the baseline only if the collector reports materially incomplete metadata/token coverage. Fix parser adapters; do not hand-edit the baseline.

- [ ] **Step 3: Freeze its hash**

```bash
sha256sum .agent-benchmarks/baseline-20260829.json \
  > .agent-benchmarks/baseline-20260829.sha256
```

This prevents accidental baseline drift during later calibration.

---

### Task 4: Add the minimal Docker Agent topology

**Files:**
- Create: `docker-agent.yaml`
- Create: `.docker-agent/instructions/lead.md`
- Create: `.docker-agent/instructions/reviewer.md`
- Create: `.docker-agent/README.md`

**Interfaces:**
- Agents: `lead`, `codex-worker`, `reviewer`
- Codex harness: `type: codex`, no model override in V1.

- [ ] **Step 1: Define a low-cost orchestration model alias**

Initial V1:

```yaml
models:
  fast:
    provider: openai
    model: gpt-5-mini
```

Keep it isolated behind the `fast` alias so one config edit changes lead/reviewer model later.

- [ ] **Step 2: Define `codex-worker`**

```yaml
agents:
  codex-worker:
    description: Bounded DJ Digger implementation worker
    harness:
      type: codex
```

No orchestration prompt is duplicated into the harness. DJ Digger `AGENTS.md` remains Codex's repository contract.

- [ ] **Step 3: Define `lead`**

Responsibilities in `lead.md`:
1. classify S/M/L risk;
2. establish ownership before delegation;
3. use CodeGraph only when ownership is unknown;
4. send one bounded task at a time;
5. invoke deterministic QA after worker handoff;
6. do not ask a model to reinterpret a passing QA result;
7. invoke reviewer only under explicit elevated-risk rules;
8. return the six-line project handoff.

Initial constraints:

```yaml
max_iterations: 8
max_tool_result_tokens: 1500
max_old_tool_call_tokens: 4000
num_history_items: 8
session_compaction: true
compaction_threshold: 0.70
redact_secrets: true
```

- [ ] **Step 4: Define `reviewer`**

Fresh context, read-only source access, bounded output. It receives:
- goal;
- changed files;
- final diff;
- relevant scoped invariant(s);
- QA result.

It does not receive the whole implementation conversation.

- [ ] **Step 5: Add shared coordination budget**

Use a named budget shared by lead/reviewer:

```yaml
budgets:
  coordination:
    max_tokens: 20000
    max_time: 10m
```

Do not assign this as a substitute for Codex quota measurement.

- [ ] **Step 6: Run Docker Agent doctor**

Use the installed Docker Agent CLI to validate the actual current schema/config. Treat documentation examples as input, not proof that the local binary accepts the file.

Expected: zero config/prerequisite errors.

---

### Task 5: Define and validate the bounded task brief

**Files:**
- Create: `.docker-agent/schemas/task-brief.schema.json`
- Modify: `.docker-agent/instructions/lead.md`

**Produces:**

```json
{
  "goal": "...",
  "risk": "S|M|L",
  "subsystem": "catalog|analysis|exports|runtime|subsystem|docs|harness",
  "owned_files": [],
  "acceptance": [],
  "scoped_instructions": [],
  "required_skill": "implement|sqlite-change|native-analysis|runtime-proof|none",
  "focused_red_green": [],
  "qa_profile_hint": "focused|subsystem|catalog|analysis|exports|runtime|full",
  "do_not_touch": [],
  "review_required": false
}
```

- [ ] **Step 1: Encode the schema**
- [ ] **Step 2: Make the lead send only these fields to Codex**
- [ ] **Step 3: Explicitly forbid repository-wide re-exploration once `owned_files` and execution path are known**
- [ ] **Step 4: Allow `owned_files` to be a subsystem glob/empty only when the lead explicitly marks ownership as unresolved and performs one exploration pass first**
- [ ] **Step 5: Keep structured-output mode off the tool-using lead in V1**

Docker Agent documentation warns that structured-output agents are best suited to single-turn use and may have limited tool-use capability. Use the JSON Schema as the handoff contract and validation target without constraining the main lead until an integration test proves structured output compatible with its tool flow.

---

### Task 6: Move final QA ownership out of Codex

**Files:**
- Create: `.docker-agent/scripts/qa-gate`
- Modify: `.codex/scripts/qa-select`
- Modify: `.codex/tests/test-harness.sh`

**Interface:**

```text
.docker-agent/scripts/qa-gate [--base REF]
```

Output on success:

```json
{"status":"pass","profile":"analysis"}
```

Output on failure is bounded and includes profile + exit status + compact diagnostic.

- [ ] **Step 1: Write harness tests for `qa-gate`**
- [ ] **Step 2: Implement `changed-files -> qa-select -> qa-run` with no model decision**
- [ ] **Step 3: Update `qa-select` so `docker-agent.yaml` and `.docker-agent/**` classify as `focused`**
- [ ] **Step 4: Keep RED/GREEN focused testing inside Codex implementation**
- [ ] **Step 5: Make Docker Agent own the final profile selection and QA gate**
- [ ] **Step 6: Ensure PASS returns no verbose logs**
- [ ] **Step 7: Ensure FAIL returns only bounded failure evidence and the retained local log path**

This removes repeated QA reasoning from Codex while preserving development-time TDD.

---

### Task 7: Add permissions, hooks, and session guards

**Files:**
- Create: `.docker-agent/scripts/session-guard`
- Modify: `docker-agent.yaml`
- Modify: `.docker-agent/README.md`

- [ ] **Step 1: Add session-start guard**

Verify:
- current directory belongs to DJ Digger;
- Git worktree is readable;
- required deterministic scripts are executable;
- protected-path guard is present.

Do not mutate the worktree.

- [ ] **Step 2: Add Docker Agent permissions**

Deny destructive operations such as:
- `sudo`;
- recursive destructive `rm`;
- `git reset`;
- `git clean`;
- automatic stash operations.

Ask for:
- `git commit`;
- `git push`.

- [ ] **Step 3: Retain `protect-local --staged` as an independent stop/delivery guard**

Do not replace a deterministic privacy guard with prompt instructions.

- [ ] **Step 4: Limit filesystem access**

Lead/reviewer read only the repository areas needed for their role. Exclude credentials and user-home secrets. Keep music/library/workspace private paths outside normal agent visibility.

- [ ] **Step 5: Enable secret redaction**

`redact_secrets: true`.

- [ ] **Step 6: Test negative paths**

Attempt representative blocked/ask operations in an isolated temporary Git repository, never in the real workspace.

---

### Task 8: Make `AGENTS.md` dual-mode instead of Docker-Agent-only

**Files:**
- Modify: `AGENTS.md`
- Modify: `.codex/skills/task/SKILL.md`
- Modify: `.codex/skills/qa/SKILL.md`
- Modify: `.codex/tests/test-harness.sh`

- [ ] **Step 1: Replace the unconditional "Codex orchestrates" rule**

New contract:
- under a Docker Agent bounded brief, Codex is the implementation worker and must not re-orchestrate;
- when invoked directly, existing Codex routing remains the fallback.

- [ ] **Step 2: Keep scoped `AGENTS.md` mandatory**
- [ ] **Step 3: Change `task` skill into fallback/direct-Codex routing**
- [ ] **Step 4: Change `qa` skill to distinguish focused RED/GREEN from external final QA gate**
- [ ] **Step 5: Do not delete `ship`, `commit`, `mr`, `runtime-proof`, `sqlite-change`, or `native-analysis`**
- [ ] **Step 6: Update harness tests for the new orchestration wording and keep line-count limits**

V1 migration is reversible and does not require Docker Agent for direct Codex sessions.

---

### Task 9: Implement risk-triggered review

**Files:**
- Modify: `.docker-agent/instructions/lead.md`
- Modify: `.docker-agent/instructions/reviewer.md`
- Create: `.docker-agent/schemas/review-result.schema.json`

**Review-required surfaces:**

```text
src/dj_digger/catalog/**
src/dj_digger/analysis/** process/worker/protocol boundaries
schemas/**
public export contracts
public CLI contract
concurrency/locking
privacy/security
cross-layer changes -> full QA
```

- [ ] **Step 1: Encode deterministic path-based mandatory-review triggers**
- [ ] **Step 2: Allow lead escalation after failed QA/rework**
- [ ] **Step 3: Pass reviewer only final diff + invariant + QA proof**
- [ ] **Step 4: Return compact verdict**

```json
{
  "verdict": "accept|changes_required",
  "blocking": [],
  "non_blocking": [],
  "residual_risk": []
}
```

- [ ] **Step 5: Do not run reviewer for ordinary S tasks**
- [ ] **Step 6: Validate review JSON in tests or a deterministic stop hook**

---

### Task 10: Add Docker Agent workflow/harness QA

**Files:**
- Modify: `.codex/tests/test-harness.sh`
- Optionally create: `tests/test_docker_agent_contract.py`

- [ ] **Step 1: Assert required files exist**
- [ ] **Step 2: Assert executable scripts**
- [ ] **Step 3: Test Docker Agent file classification as `focused`**
- [ ] **Step 4: Test task-brief and review schemas**
- [ ] **Step 5: Test privacy guards**
- [ ] **Step 6: Run `docker agent doctor` as an explicit environment smoke test**

Do not make the ordinary Python test suite fail solely because Docker Agent is not installed on a machine that is not used for agentic development. Keep the Docker Agent binary smoke check explicit.

---

### Task 11: Pilot the new workflow without deleting old behavior

**No new production files.**

Use real upcoming DJ Digger work rather than synthetic feature work.

- [ ] **Step 1: Run at least 3 S tasks**
- [ ] **Step 2: Run at least 3 M tasks**
- [ ] **Step 3: Run at least 2 L/high-risk tasks**
- [ ] **Step 4: Confirm direct `codex` fallback still works**
- [ ] **Step 5: Record only deterministic run outcomes; do not tune limits mid-sample unless a correctness bug requires it**

This gives enough variety to detect whether savings come only from easy tasks.

---

### Task 12: Capture post-migration Codex data and compare

**Generated files only:**
- `.agent-benchmarks/after-YYYYMMDD.json`
- `.agent-benchmarks/comparison-YYYYMMDD.json`

- [ ] **Step 1: Collect the same number of latest post-migration root sessions**

```bash
.docker-agent/scripts/codex-session-benchmark \
  --repo . \
  --limit 20 \
  --output .agent-benchmarks/after-2026MMDD.json
```

Use the same selection/collector version as baseline, or explicitly migrate both reports before comparison.

- [ ] **Step 2: Run comparison**

```bash
.docker-agent/scripts/benchmark-compare \
  .agent-benchmarks/baseline-20260829.json \
  .agent-benchmarks/after-2026MMDD.json \
  --output .agent-benchmarks/comparison-2026MMDD.json
```

- [ ] **Step 3: Evaluate initial targets**

Primary:
- median Codex total tokens/session <= baseline * 0.70.

Secondary:
- lower root user-turn median;
- lower repeated discovery median;
- no worse final QA pass behavior;
- no increase in QA repair/post-review rework;
- bounded coordination overhead.

- [ ] **Step 4: Keep task-complexity caveat explicit**

Do not claim a causal percentage improvement from unmatched workloads. Report the raw distributions and S/M/L mix alongside the aggregate comparison.

---

### Task 13: Calibrate from evidence

**Files potentially modified:**
- `docker-agent.yaml`
- `.docker-agent/instructions/lead.md`
- review trigger configuration if extracted into a deterministic file

Only after the pilot sample.

Evaluate one variable at a time:
1. lead model;
2. `max_iterations`;
3. tool-result caps;
4. history limit;
5. compaction threshold;
6. mandatory-review surface;
7. coordination token budget.

Do not introduce extra permanent agents unless benchmark data shows a specific repeated workload that cannot be handled efficiently by lead + Codex + reviewer.

Code Mode and additional MCP/tooling remain deferred until call-chain data shows they solve an observed bottleneck.

---

## Verification matrix

| Area | Required proof |
|---|---|
| Benchmark parser | synthetic legacy + paginated rollouts pass |
| Multi-agent accounting | root + children aggregate once |
| Token accounting | cumulative snapshots are not double-counted |
| Privacy | no prompt/response/raw command/absolute path in output |
| Benchmark comparison | median/p75/delta deterministic |
| Docker Agent config | `docker agent doctor` passes |
| QA routing | Docker Agent files -> `focused`; cross-layer source -> existing `full` behavior |
| QA gate | compact PASS; bounded FAIL |
| Direct Codex fallback | existing harness tests pass |
| Permissions | destructive operations blocked/asked in isolated test |
| Review routing | high-risk paths reviewed; S tasks not reviewed |
| Final repository QA | existing appropriate DJ Digger QA profile passes |

## Expected V1 outcome

The workflow is considered ready for normal use when:
1. baseline is frozen;
2. Docker Agent config passes doctor;
3. benchmark/harness tests pass;
4. direct Codex remains functional;
5. pilot tasks complete without bypassing privacy/Git rules;
6. post-run comparison shows measurable Codex savings without QA regression.

The first optimization target is not maximum autonomy. It is less repeated model work per verified change.
