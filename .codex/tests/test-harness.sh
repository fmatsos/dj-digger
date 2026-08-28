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

grep -q "current_track_analysis, BEGIN IMMEDIATE" "$ROOT/src/dj_digger/catalog/AGENTS.md"
grep -q "parent-only SQLite, protocol_version" "$ROOT/src/dj_digger/analysis/AGENTS.md"
grep -q "atomic replacement, one SQLite snapshot" "$ROOT/src/dj_digger/exports/AGENTS.md"
grep -q "observable RED, public composition" "$ROOT/tests/AGENTS.md"
grep -q "read-only source library" "$ROOT/scripts/AGENTS.md"
grep -q "tracks.tsv, same export run" "$ROOT/skills/AGENTS.md"
grep -q "historical plans, explicit staging" "$ROOT/docs/AGENTS.md"

for script in project-env changed-files protect-local
do
  test -x "$ROOT/.codex/scripts/$script"
done
env_output=$(.codex/scripts/project-env sh -c 'printf "%s|%s" "$UV_CACHE_DIR" "$UV_TOOL_DIR"')
test "$env_output" = "/tmp/dj-digger-uv-cache|/tmp/dj-digger-uv-tools"
.codex/scripts/changed-files | LC_ALL=C sort -c

# Test protect-local in isolated mktemp repo
(
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  cd "$tmpdir"
  git init -q
  git config user.email "test@example.com"
  git config user.name "Test User"

  # Create initial commit for git diff to work
  echo "init" > README.md
  git add README.md
  git commit -q -m "init"

  # Test 1: protected files should fail
  for path in config/local.toml workspace/export.tsv sets/demo.m3u8 catalog.sqlite catalog.sqlite3 docs/superpowers/specs/demo.md
  do
    mkdir -p "$(dirname "$path")"
    echo "content" > "$path"
    git add "$path"
  done
  "$ROOT/.codex/scripts/protect-local" --staged 2>/dev/null && exit 1

  # Test 2: reset staging and test with safe file
  git reset -q
  mkdir -p src
  echo "safe" > src/example.py
  git add src/example.py
  "$ROOT/.codex/scripts/protect-local" --staged

  # Test 3: spec file should fail without env var
  git reset -q
  mkdir -p docs/superpowers/specs
  echo "spec" > docs/superpowers/specs/demo.md
  git add docs/superpowers/specs/demo.md
  "$ROOT/.codex/scripts/protect-local" --staged 2>/dev/null && exit 1

  # Test 4: spec file should pass with DJ_DIGGER_ALLOW_SPEC_STAGE=1
  DJ_DIGGER_ALLOW_SPEC_STAGE=1 "$ROOT/.codex/scripts/protect-local" --staged

  git reset -q
  git add catalog.sqlite3
  git commit -q -m "add protected catalog"
  ! "$ROOT/.codex/scripts/protect-local" --range HEAD^..HEAD 2>/dev/null
)

# Test qa-select classification rules
test "$(printf 'README.md\n' | "$ROOT/.codex/scripts/qa-select")" = "docs"
test "$(printf 'src/dj_digger/copying/set_copy.py\n' | "$ROOT/.codex/scripts/qa-select")" = "subsystem"
test "$(printf 'src/dj_digger/catalog/migrations.py\n' | "$ROOT/.codex/scripts/qa-select")" = "catalog"
test "$(printf 'src/dj_digger/catalog/sql/catalog-v7.sql\n' | "$ROOT/.codex/scripts/qa-select")" = "catalog"
test "$(printf 'src/dj_digger/analysis/worker_client.py\n' | "$ROOT/.codex/scripts/qa-select")" = "analysis"
test "$(printf 'src/dj_digger/exports/tracks.py\n' | "$ROOT/.codex/scripts/qa-select")" = "exports"
test "$(printf 'src/dj_digger/cli.py\n' | "$ROOT/.codex/scripts/qa-select")" = "runtime"
test "$(printf 'src/dj_digger/cli.py\nsrc/dj_digger/catalog/migrations.py\n' | "$ROOT/.codex/scripts/qa-select")" = "full"

# Test qa-select does not escalate a docs+single-production-category change to
# full: docs must be filtered out of the production-category count just like
# focused is.
test "$(printf 'README.md\nsrc/dj_digger/catalog/migrations.py\n' | "$ROOT/.codex/scripts/qa-select")" = "catalog"

# Test qa-run focused profile (run simple test script)
test "$("$ROOT/.codex/scripts/qa-run" focused -- "$ROOT/.codex/tests/simple-test.sh")" = "PASS focused"

# Test qa-run reports a real failure (not a false PASS) when the underlying
# command fails. This is a regression test for the `if ! cmd; then status=$?`
# bug where `$?` inside the `then` branch is the negation test's own status
# (always 0), not the command's real exit code.
(
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  failing_script="$tmpdir/fail.sh"
  printf '#!/bin/sh\nexit 3\n' > "$failing_script"
  chmod +x "$failing_script"

  set +e
  output=$("$ROOT/.codex/scripts/qa-run" focused -- "$failing_script" 2>/dev/null)
  rc=$?
  set -e

  test "$rc" -ne 0
  case "$output" in
    "PASS focused")
      printf 'qa-run negative-path regression: got false PASS\n' >&2
      exit 1
      ;;
  esac
)

# Test staged-check in isolated mktemp repo
(
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  cd "$tmpdir"
  git init -q
  git config user.email "test@example.com"
  git config user.name "Test User"

  # Create initial commit for git diff to work
  echo "init" > README.md
  git add README.md
  git commit -q -m "init"

  # Test 1: staged-check passes when only allowed path is staged
  mkdir -p src
  echo "content" > src/example.py
  git add src/example.py
  "$ROOT/.codex/scripts/staged-check" src/example.py
  git reset -q

  # Test 2: staged-check fails with extra staged path
  mkdir -p src
  echo "content" > src/example.py
  echo "extra" > src/extra.py
  git add src/example.py src/extra.py
  ! "$ROOT/.codex/scripts/staged-check" src/example.py 2>/dev/null
  git reset -q

  # Test 3: staged-check rejects protected paths via protect-local
  mkdir -p config
  echo "protected" > config/local.toml
  git add config/local.toml
  ! "$ROOT/.codex/scripts/staged-check" config/local.toml 2>/dev/null
  git reset -q

  # Test 4: staged-check rejects conflict markers
  mkdir -p src
  echo "line1
<<<<<<<
conflict
=======
other
>>>>>>>
line2" > src/example.py
  git add src/example.py
  ! "$ROOT/.codex/scripts/staged-check" src/example.py 2>/dev/null
)

# Test handoff script output format
(
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  cd "$tmpdir"
  git init -q
  git config user.email "test@example.com"
  git config user.name "Test User"
  git checkout -q -b test-branch 2>/dev/null || git symbolic-ref HEAD refs/heads/test-branch

  # Create initial commit
  echo "init" > README.md
  git add README.md
  git commit -q -m "init"

  # Test handoff output has exactly 6 lines with expected headings
  output=$("$ROOT/.codex/scripts/handoff")
  lines=$(printf '%s\n' "$output" | wc -l)
  test "$lines" = 6

  # Check for expected headings (each on its own line followed by value)
  printf '%s\n' "$output" | grep -q '^Status:'
  printf '%s\n' "$output" | grep -q '^Branch:'
  printf '%s\n' "$output" | grep -q '^Diff:'
  printf '%s\n' "$output" | grep -q '^QA:'
  printf '%s\n' "$output" | grep -q '^Next:'
  printf '%s\n' "$output" | grep -q '^Risk:'
)

# Test handoff's Diff field carries real shortstat content for a known change,
# not the digit-mash produced by stripping a --stat summary line with a
# pipe-anchored sed (a --stat summary line has no "|" to strip).
(
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  cd "$tmpdir"
  git init -q
  git config user.email "test@example.com"
  git config user.name "Test User"

  echo "init" > README.md
  git add README.md
  git commit -q -m "init"

  echo "line1" >> README.md
  echo "line2" >> README.md
  git add README.md

  diff_line=$("$ROOT/.codex/scripts/handoff" | grep '^Diff:')
  printf '%s\n' "$diff_line" | grep -q "insertion"
  printf '%s\n' "$diff_line" | grep -q "file"
)

# Test skill structure and content
for skill in task implement qa runtime-proof sqlite-change native-analysis commit mr ship
do
  skill_file="$ROOT/.codex/skills/$skill/SKILL.md"
  test -f "$skill_file"

  # Check frontmatter starts with ---
  head -1 "$skill_file" | grep -q "^---"

  # Check frontmatter ends with --- (should be around line 2-5)
  head -10 "$skill_file" | tail -9 | grep -q "^---"

  # Check contains name: field
  grep -q "^name:" "$skill_file"

  # Check contains description: field
  grep -q "^description:" "$skill_file"

  # Check line count <= 140
  lines=$(wc -l < "$skill_file")
  test "$lines" -le 140
done

# Verify root AGENTS.md names all nine skills in the Skill routing section
# (backticked, as they appear there) rather than merely containing common
# English words that would pass even if no skill were actually named.
grep -q '`task`' "$AGENTS"
grep -q '`implement`' "$AGENTS"
grep -q '`qa`' "$AGENTS"
grep -q '`runtime-proof`' "$AGENTS"
grep -q '`sqlite-change`' "$AGENTS"
grep -q '`native-analysis`' "$AGENTS"
grep -q '`commit`' "$AGENTS"
grep -q '`mr`' "$AGENTS"
grep -q '`ship`' "$AGENTS"

# Test hooks.json configuration
hooks_file="$ROOT/.codex/hooks.json"
test -f "$hooks_file"

# Test 1: JSON validity
python3 -m json.tool "$hooks_file" >/dev/null

# Test 2: UserPromptSubmit has conditional codegraph prompt-hook
grep -q "UserPromptSubmit" "$hooks_file"
grep -q "codegraph prompt-hook" "$hooks_file"
grep -q "if command -v codegraph" "$hooks_file"

# Test 3: Stop has protect-local --staged
grep -q "Stop" "$hooks_file"
grep -q "protect-local --staged" "$hooks_file"

# Test 4: No PreToolUse hook anywhere in hooks.json
! grep -q "PreToolUse" "$hooks_file"

# Test 5: No destructive Git commands (commit, push, checkout, reset, clean)
! grep -q "git commit" "$hooks_file"
! grep -q "git push" "$hooks_file"
! grep -q "git checkout" "$hooks_file"
! grep -q "git reset" "$hooks_file"
! grep -q "git clean" "$hooks_file"

# Test 6: No cleanup or full-QA commands
! grep -qE "cleanup|full-qa|full_qa|teardown" "$hooks_file"
