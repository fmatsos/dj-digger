# Codex Development Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Codex-only, token-efficient development harness with concise hierarchical instructions, risk-routed skills, deterministic QA and safety scripts, and minimal native hooks.

**Architecture:** A root `AGENTS.md` carries permanent invariants and routes conditional work into project skills. Nested `AGENTS.md` files add only directory-specific rules; shell scripts implement deterministic checks; `.codex/hooks.json` registers only the verified CodeGraph prompt hook and a silent protected-file stop check.

**Tech Stack:** Codex CLI 0.150.1, Markdown `AGENTS.md`, Codex `SKILL.md`, JSON hooks, POSIX shell, Git, uv, pytest, Ruff, mypy, Python 3.12.

---

## File map

| File | Responsibility |
| --- | --- |
| `AGENTS.md` | Permanent project contract, model policy, navigation, proof and skill routing |
| `src/dj_digger/AGENTS.md` | Shared Python/application rules |
| `src/dj_digger/{catalog,analysis,exports}/AGENTS.md` | Subsystem invariants |
| `{tests,scripts,skills,docs}/AGENTS.md` | Scope-specific test, acceptance, curation and documentation rules |
| `.codex/scripts/project-env` | Run commands with supported uv caches |
| `.codex/scripts/changed-files` | Return normalized changed paths |
| `.codex/scripts/protect-local` | Reject protected modified or staged paths |
| `.codex/scripts/qa-select` | Map changed files to the minimum QA profile |
| `.codex/scripts/qa-run` | Execute compact risk-proportional QA |
| `.codex/scripts/package-check` | Verify packaged runtime resources |
| `.codex/scripts/staged-check` | Validate staged delivery scope |
| `.codex/scripts/handoff` | Print a compact resumption report |
| `.codex/hooks.json` | Verified Codex lifecycle hooks |
| `.codex/tests/test-harness.sh` | Structural, routing, protection and selector tests |
| `.codex/skills/*/SKILL.md` | On-demand development workflows |

The design proposed a generic `runtime-smoke` script. YAGNI applies: public commands
vary by feature, so `runtime-proof` will select explicit existing tests and commands.

### Task 1: Add the root Codex contract

**Owner/model:** GPT-5.6 Sol low  
**Files:**
- Create: `AGENTS.md`
- Create: `.codex/tests/test-harness.sh`

- [ ] **Step 1: Write the failing structural test**

Create the executable test with:

```sh
#!/bin/sh
set -eu
ROOT=$(git rev-parse --show-toplevel)
AGENTS="$ROOT/AGENTS.md"
test -f "$AGENTS"
lines=$(wc -l < "$AGENTS")
test "$lines" -lt 200
grep -q "GPT-5.6 Sol" "$AGENTS"
grep -q "GPT-5.6 Luna" "$AGENTS"
grep -q "CodeGraph" "$AGENTS"
grep -Eq "COMPLETE.*PARTIAL.*BLOCKED" "$AGENTS"
```

- [ ] **Step 2: Verify RED**

Run: `sh .codex/tests/test-harness.sh`  
Expected: non-zero because `AGENTS.md` is absent.

- [ ] **Step 3: Write `AGENTS.md`**

Use exactly these sections:

```markdown
# DJ Digger Agent Contract
## Mission and architecture
## Instruction scope
## Exploration order
## Permanent invariants
## Models and delegation
## Observable proof
## Risk-based QA
## Git and privacy
## Skill routing
## Completion report
```

Keep it at 120–160 lines. Assign architecture, supervision and final review to Sol
low; simple implementation to Luna low; complex implementation and targeted
independent review to Luna medium. Include the bounded worker brief fields from the
design and require the closest scoped `AGENTS.md` before editing.

- [ ] **Step 4: Verify GREEN**

Run: `sh .codex/tests/test-harness.sh && wc -l AGENTS.md`  
Expected: PASS and fewer than 200 lines.

- [ ] **Step 5: Checkpoint**

Run: `git diff --check -- AGENTS.md .codex/tests/test-harness.sh`  
Expected: no output. Do not commit without a separate Git delivery request.

### Task 2: Add directory-scoped instructions

**Owner/model:** GPT-5.6 Luna low  
**Review:** GPT-5.6 Sol low  
**Files:**
- Create: `src/dj_digger/AGENTS.md`
- Create: `src/dj_digger/catalog/AGENTS.md`
- Create: `src/dj_digger/analysis/AGENTS.md`
- Create: `src/dj_digger/exports/AGENTS.md`
- Create: `tests/AGENTS.md`
- Create: `scripts/AGENTS.md`
- Create: `skills/AGENTS.md`
- Create: `docs/AGENTS.md`
- Modify: `.codex/tests/test-harness.sh`

- [ ] **Step 1: Add failing scoped-file checks**

Append:

```sh
for file in \
  src/dj_digger/AGENTS.md \
  src/dj_digger/catalog/AGENTS.md \
  src/dj_digger/analysis/AGENTS.md \
  src/dj_digger/exports/AGENTS.md \
  tests/AGENTS.md scripts/AGENTS.md skills/AGENTS.md docs/AGENTS.md
do
  test -f "$ROOT/$file"
  lines=$(wc -l < "$ROOT/$file")
  test "$lines" -le 100
done
```

- [ ] **Step 2: Verify RED**

Run: `sh .codex/tests/test-harness.sh`  
Expected: non-zero at the first missing scoped file.

- [ ] **Step 3: Create the eight scoped files**

Use the approved design, imperative rules, 30–80 lines each, and no duplication of
the global model, Git or completion policies. Required unique anchors:

```text
catalog  -> current_track_analysis, BEGIN IMMEDIATE
analysis -> parent-only SQLite, protocol_version
exports  -> atomic replacement, one SQLite snapshot
tests    -> observable RED, public composition
scripts  -> read-only source library
skills   -> tracks.tsv, same export run
docs     -> historical plans, explicit staging
```

- [ ] **Step 4: Verify GREEN**

Add `grep -q` assertions for those anchors and run:

```sh
sh .codex/tests/test-harness.sh
git diff --check -- AGENTS.md src tests/AGENTS.md scripts/AGENTS.md skills/AGENTS.md docs/AGENTS.md
```

Expected: PASS and no diff-check output.

- [ ] **Step 5: Sol scope review**

Reject duplicated paragraphs, generic advice, misplaced rules, or private paths.
Do not commit without explicit Git delivery authorization.

### Task 3: Implement environment and changed-file primitives

**Owner/model:** GPT-5.6 Luna low  
**Files:**
- Create: `.codex/scripts/project-env`
- Create: `.codex/scripts/changed-files`
- Modify: `.codex/tests/test-harness.sh`

- [ ] **Step 1: Add failing executable and behavior tests**

Append:

```sh
for script in project-env changed-files
do
  test -x "$ROOT/.codex/scripts/$script"
done
env_output=$(.codex/scripts/project-env sh -c 'printf "%s|%s" "$UV_CACHE_DIR" "$UV_TOOL_DIR"')
test "$env_output" = "/tmp/dj-digger-uv-cache|/tmp/dj-digger-uv-tools"
.codex/scripts/changed-files | LC_ALL=C sort -c
```

- [ ] **Step 2: Verify RED**

Run: `sh .codex/tests/test-harness.sh`  
Expected: non-zero because the scripts are absent.

- [ ] **Step 3: Implement `project-env`**

```sh
#!/bin/sh
set -eu
export UV_CACHE_DIR=/tmp/dj-digger-uv-cache
export UV_TOOL_DIR=/tmp/dj-digger-uv-tools
exec "$@"
```

- [ ] **Step 4: Implement `changed-files`**

```sh
#!/bin/sh
set -eu
root=$(git rev-parse --show-toplevel)
cd "$root"
{
  git diff --name-only
  git diff --cached --name-only
  git ls-files --others --exclude-standard
} | sed '/^$/d' | LC_ALL=C sort -u
```

- [ ] **Step 5: Verify GREEN**

Run:

```sh
chmod +x .codex/scripts/project-env .codex/scripts/changed-files .codex/tests/test-harness.sh
sh .codex/tests/test-harness.sh
```

Expected: PASS.

### Task 4: Implement protected-path checks

**Owner/model:** GPT-5.6 Luna medium  
**Review:** GPT-5.6 Sol low  
**Files:**
- Create: `.codex/scripts/protect-local`
- Modify: `.codex/tests/test-harness.sh`

- [ ] **Step 1: Add isolated failing tests**

In a `mktemp -d` Git repository, stage each of
`config/local.toml`, `workspace/export.tsv`, `sets/demo.m3u8`,
`catalog.sqlite`, and `docs/superpowers/specs/demo.md`; assert
`protect-local --staged` fails. Assert staged `src/example.py` passes. Use a trap
that removes only the resolved temporary repository.

- [ ] **Step 2: Verify RED**

Run: `sh .codex/tests/test-harness.sh`  
Expected: non-zero because `protect-local` is absent.

- [ ] **Step 3: Implement `protect-local`**

Accept exactly `--changed` or `--staged`. Reject unknown arguments with exit 2.
Classify paths with:

```sh
case "$path" in
  config/local.toml|workspace/*|sets/*|*.sqlite|*.sqlite-wal|*.sqlite-shm)
    printf 'protected local path: %s\n' "$path" >&2
    failed=1
    ;;
  docs/superpowers/specs/*)
    if test "${DJ_DIGGER_ALLOW_SPEC_STAGE:-0}" != 1; then
      printf 'spec staging requires DJ_DIGGER_ALLOW_SPEC_STAGE=1: %s\n' "$path" >&2
      failed=1
    fi
    ;;
esac
```

Exit 0 silently when no violation exists.

- [ ] **Step 4: Verify authorized specs and GREEN**

Assert `DJ_DIGGER_ALLOW_SPEC_STAGE=1 protect-local --staged` accepts a spec-only
fixture. Run `sh .codex/tests/test-harness.sh`; expected: PASS.

- [ ] **Step 5: Sol safety review**

Verify path quoting, spaces, exact temporary cleanup, and absence of destructive
operations against the real repository.

### Task 5: Implement QA selection and compact execution

**Owner/model:** GPT-5.6 Luna medium  
**Review:** GPT-5.6 Sol low  
**Files:**
- Create: `.codex/scripts/qa-select`
- Create: `.codex/scripts/qa-run`
- Create: `.codex/scripts/package-check`
- Modify: `.codex/tests/test-harness.sh`

- [ ] **Step 1: Add table-driven failing selector tests**

Pipe paths to `qa-select` and assert:

```text
README.md                                   -> docs
src/dj_digger/copying/set_copy.py           -> subsystem
src/dj_digger/catalog/migrations.py         -> catalog
src/dj_digger/catalog/sql/catalog-v7.sql    -> catalog
src/dj_digger/analysis/worker_client.py      -> analysis
src/dj_digger/exports/tracks.py              -> exports
src/dj_digger/cli.py                         -> runtime
cli.py plus catalog/migrations.py            -> full
```

- [ ] **Step 2: Verify RED**

Run: `sh .codex/tests/test-harness.sh`  
Expected: non-zero because `qa-select` is absent.

- [ ] **Step 3: Implement `qa-select`**

Read newline-delimited paths, count distinct production categories, and print exactly
one of `docs`, `focused`, `subsystem`, `catalog`, `analysis`, `exports`,
`runtime`, or `full`. Multiple production categories produce `full`; instruction
and harness files produce `focused`.

- [ ] **Step 4: Implement `package-check`**

Run `uv build --wheel`, unpack into a resolved temporary directory, and assert
`analysis.toml`, `schema-bundle.json`, packaged schemas, and catalog migration SQL
are present. Clean only that temporary directory through a trap.

- [ ] **Step 5: Implement `qa-run`**

Accept one profile and execute:

```text
docs      -> git diff --check
focused   -> pytest targets passed after --
subsystem -> relevant pytest plus Ruff on changed Python
catalog   -> catalog/migration tests plus package-check
analysis  -> worker/pipeline tests plus Ruff and mypy
exports   -> export/schema tests plus fixture validation
runtime   -> CLI/application tests plus Ruff and mypy
full      -> full pytest, Ruff, mypy, fixtures, package-check, diff check
```

Run uv commands through `project-env`. Capture full output in `mktemp -d`; print one
PASS line or the failing command, relevant tail, and log path.

- [ ] **Step 6: Verify GREEN**

Run:

```sh
sh .codex/tests/test-harness.sh
.codex/scripts/qa-run docs
```

Expected: test PASS and `PASS docs`.

### Task 6: Add staged delivery and handoff scripts

**Owner/model:** GPT-5.6 Luna low  
**Files:**
- Create: `.codex/scripts/staged-check`
- Create: `.codex/scripts/handoff`
- Modify: `.codex/tests/test-harness.sh`

- [ ] **Step 1: Add failing isolated tests**

In a temporary repository, assert `staged-check src/example.py` passes when only that
path is staged, fails with an extra staged path, and calls protected-path validation.
Assert `handoff` prints exactly `Status`, `Branch`, `Diff`, `QA`, `Next`,
and `Risk` headings.

- [ ] **Step 2: Implement `staged-check`**

Require at least one allowed path. Compare sorted staged and allowed lists, run
`protect-local --staged`, reject conflict markers in staged content, and run
`git diff --cached --check`. Print `PASS staged scope` only on success.

- [ ] **Step 3: Implement `handoff`**

Accept `--status`, `--qa`, `--next`, and `--risk`; derive branch and compact
diff summary; print six single-line fields. Exclude protected untracked names and all
file contents.

- [ ] **Step 4: Verify GREEN**

Run: `sh .codex/tests/test-harness.sh`  
Expected: PASS.

### Task 7: Create the seven project skills

**Owner/model:** GPT-5.6 Luna medium  
**Review:** GPT-5.6 Sol low  
**Files:**
- Create: `.codex/skills/task/SKILL.md`
- Create: `.codex/skills/implement/SKILL.md`
- Create: `.codex/skills/qa/SKILL.md`
- Create: `.codex/skills/runtime-proof/SKILL.md`
- Create: `.codex/skills/sqlite-change/SKILL.md`
- Create: `.codex/skills/native-analysis/SKILL.md`
- Create: `.codex/skills/ship/SKILL.md`
- Modify: `.codex/tests/test-harness.sh`

- [ ] **Step 1: Add failing skill-structure tests**

For every skill, assert `SKILL.md` exists, begins and ends frontmatter correctly,
contains `name:` and `description:`, and stays at or below 140 lines. Assert the
root `AGENTS.md` names all seven skills.

- [ ] **Step 2: Verify RED**

Run: `sh .codex/tests/test-harness.sh`  
Expected: non-zero at the first missing skill.

- [ ] **Step 3: Write `task`, `implement`, and `qa`**

`task` owns risk/model routing; `implement` owns observable RED/GREEN; `qa` calls
`qa-select` and `qa-run`. Use the exact compact outputs from the design and do not
repeat repository architecture.

- [ ] **Step 4: Write the three risk skills**

`runtime-proof` checks real composition, exits, state and artifacts.
`sqlite-change` checks rollback, foreign keys, projections, concurrency and packaged
SQL. `native-analysis` checks Python 3.12, OOM evidence, workers, IPC, parent-only
persistence and honest real-library limitations.

- [ ] **Step 5: Write `ship`**

Require an explicit commit/push request, call `staged-check`, verify local and remote
HEAD, never stage with `.`, never delete a branch without authorization and ancestry
proof, and never stage specs without current explicit authorization.

- [ ] **Step 6: Verify GREEN and perform Sol review**

Run `sh .codex/tests/test-harness.sh`; expected PASS. Sol removes duplicated prose,
unnecessary agents, generic QA claims, and private-library details.

### Task 8: Register minimal native Codex hooks

**Owner/model:** GPT-5.6 Luna low  
**Review:** GPT-5.6 Sol low  
**Files:**
- Create: `.codex/hooks.json`
- Modify: `.codex/tests/test-harness.sh`

- [ ] **Step 1: Add failing hook tests**

Assert JSON validity, a conditional `codegraph prompt-hook` under
`UserPromptSubmit`, and `protect-local --staged` under `Stop`. Assert no
`PreToolUse`, destructive Git, commit, push, cleanup, or full QA command appears.

- [ ] **Step 2: Create the verified hook map**

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "if command -v codegraph >/dev/null 2>&1; then exec codegraph prompt-hook; fi"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".codex/scripts/protect-local --staged"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Verify configuration**

Run:

```sh
python3 -m json.tool .codex/hooks.json >/dev/null
codex --strict-config features list >/dev/null
sh .codex/tests/test-harness.sh
```

Expected: exit 0. Do not bypass Codex's first-discovery hook trust prompt.

- [ ] **Step 4: Sol hook review**

Confirm success is silent, no arbitrary command interception exists, expensive QA is
not automatic, and hooks cannot mutate the worktree.

### Task 9: Run full harness acceptance and handoff

**Owner/model:** GPT-5.6 Sol low  
**Files:**
- Modify only if acceptance finds a defect: files created in Tasks 1–8

- [ ] **Step 1: Run structural and dry-run acceptance**

Run: `sh .codex/tests/test-harness.sh`  
Expected: PASS without modifying `config/local.toml`, `sets/`, or `workspace/`.

- [ ] **Step 2: Measure instruction volume**

Run:

```sh
wc -l AGENTS.md src/dj_digger/AGENTS.md src/dj_digger/catalog/AGENTS.md \
  src/dj_digger/analysis/AGENTS.md src/dj_digger/exports/AGENTS.md \
  tests/AGENTS.md scripts/AGENTS.md skills/AGENTS.md docs/AGENTS.md
```

Expected: root below 200; every scope at or below 100.

- [ ] **Step 3: Run differential harness QA**

Run:

```sh
.codex/scripts/qa-run focused -- .codex/tests/test-harness.sh
.codex/scripts/protect-local --staged
git diff --check
```

Expected: PASS. Run full repository QA only if production or packaging files changed.

- [ ] **Step 4: Inspect final scope**

Run `git status --short --branch`, `git diff --stat`, and inspect the complete
harness diff. Confirm pre-existing untracked paths are unchanged and unstaged.

- [ ] **Step 5: Produce the handoff**

```sh
.codex/scripts/handoff \
  --status COMPLETE \
  --qa "harness tests, protected-path dry runs, diff check" \
  --next "user review; commit only if requested" \
  --risk "Codex will request trust for newly discovered repository hooks"
```

Expected: six concise lines without private paths or contents.

- [ ] **Step 6: Stop before Git delivery**

Present created files, line counts, verification, hook trust, and risks. Do not stage,
commit, push, or clean branches until explicitly requested.

