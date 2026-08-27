#!/bin/sh
set -eu
ROOT=$(git rev-parse --show-toplevel)
CLAUDE_MD="$ROOT/CLAUDE.md"
test -f "$CLAUDE_MD"
lines=$(wc -l < "$CLAUDE_MD")
test "$lines" -lt 200
grep -q "CodeGraph" "$CLAUDE_MD"
grep -Eq "COMPLETE.*PARTIAL.*BLOCKED" "$CLAUDE_MD"
! grep -q "GPT-5.6" "$CLAUDE_MD"
grep -q "Sonnet" "$CLAUDE_MD"
grep -q "Haiku" "$CLAUDE_MD"

for file in \
  src/dj_digger/CLAUDE.md \
  src/dj_digger/catalog/CLAUDE.md \
  src/dj_digger/analysis/CLAUDE.md \
  src/dj_digger/exports/CLAUDE.md \
  tests/CLAUDE.md scripts/CLAUDE.md skills/CLAUDE.md docs/CLAUDE.md
do
  test -f "$ROOT/$file"
  lines=$(wc -l < "$ROOT/$file")
  test "$lines" -le 100
  ! grep -q "GPT-5.6" "$ROOT/$file"
  ! grep -q "AGENTS.md" "$ROOT/$file"
done

grep -q "current_track_analysis, BEGIN IMMEDIATE" "$ROOT/src/dj_digger/catalog/CLAUDE.md"
grep -q "parent-only SQLite, protocol_version" "$ROOT/src/dj_digger/analysis/CLAUDE.md"
grep -q "atomic replacement, one SQLite snapshot" "$ROOT/src/dj_digger/exports/CLAUDE.md"
grep -q "observable RED, public composition" "$ROOT/tests/CLAUDE.md"
grep -q "read-only source library" "$ROOT/scripts/CLAUDE.md"
grep -q "tracks.tsv, same export run" "$ROOT/skills/CLAUDE.md"
grep -q "historical plans, explicit staging" "$ROOT/docs/CLAUDE.md"

for script in project-env changed-files protect-local
do
  test -x "$ROOT/.claude/scripts/$script"
done
env_output=$(.claude/scripts/project-env sh -c 'printf "%s|%s" "$UV_CACHE_DIR" "$UV_TOOL_DIR"')
test "$env_output" = "/tmp/dj-digger-uv-cache|/tmp/dj-digger-uv-tools"
.claude/scripts/changed-files | LC_ALL=C sort -c

# Verify every symlink under .claude/scripts/ resolves to the corresponding
# .codex/scripts/ file (same content, no forked logic) and is executable.
for script in changed-files handoff package-check project-env protect-local qa-run qa-select staged-check
do
  link="$ROOT/.claude/scripts/$script"
  target="$ROOT/.codex/scripts/$script"
  test -L "$link"
  test -x "$link"
  resolved=$(readlink -f "$link")
  expected=$(readlink -f "$target")
  test "$resolved" = "$expected"
done

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
  for path in config/local.toml workspace/export.tsv sets/demo.m3u8 catalog.sqlite docs/superpowers/specs/demo.md
  do
    mkdir -p "$(dirname "$path")"
    echo "content" > "$path"
    git add "$path"
  done
  "$ROOT/.claude/scripts/protect-local" --staged 2>/dev/null && exit 1

  # Test 2: reset staging and test with safe file
  git reset -q
  mkdir -p src
  echo "safe" > src/example.py
  git add src/example.py
  "$ROOT/.claude/scripts/protect-local" --staged

  # Test 3: spec file should fail without env var
  git reset -q
  mkdir -p docs/superpowers/specs
  echo "spec" > docs/superpowers/specs/demo.md
  git add docs/superpowers/specs/demo.md
  "$ROOT/.claude/scripts/protect-local" --staged 2>/dev/null && exit 1

  # Test 4: spec file should pass with DJ_DIGGER_ALLOW_SPEC_STAGE=1
  DJ_DIGGER_ALLOW_SPEC_STAGE=1 "$ROOT/.claude/scripts/protect-local" --staged
)

# Test qa-select classification rules
test "$(printf 'README.md\n' | "$ROOT/.claude/scripts/qa-select")" = "docs"
test "$(printf 'src/dj_digger/copying/set_copy.py\n' | "$ROOT/.claude/scripts/qa-select")" = "subsystem"
test "$(printf 'src/dj_digger/catalog/migrations.py\n' | "$ROOT/.claude/scripts/qa-select")" = "catalog"
test "$(printf 'src/dj_digger/catalog/sql/catalog-v7.sql\n' | "$ROOT/.claude/scripts/qa-select")" = "catalog"
test "$(printf 'src/dj_digger/analysis/worker_client.py\n' | "$ROOT/.claude/scripts/qa-select")" = "analysis"
test "$(printf 'src/dj_digger/exports/tracks.py\n' | "$ROOT/.claude/scripts/qa-select")" = "exports"
test "$(printf 'src/dj_digger/cli.py\n' | "$ROOT/.claude/scripts/qa-select")" = "runtime"
test "$(printf 'src/dj_digger/cli.py\nsrc/dj_digger/catalog/migrations.py\n' | "$ROOT/.claude/scripts/qa-select")" = "full"

# Test qa-select does not escalate a docs+single-production-category change to
# full: docs must be filtered out of the production-category count just like
# focused is.
test "$(printf 'README.md\nsrc/dj_digger/catalog/migrations.py\n' | "$ROOT/.claude/scripts/qa-select")" = "catalog"

# Test qa-run focused profile (run simple test script)
test "$("$ROOT/.claude/scripts/qa-run" focused -- "$ROOT/.codex/tests/simple-test.sh")" = "PASS focused"

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
  output=$("$ROOT/.claude/scripts/qa-run" focused -- "$failing_script" 2>/dev/null)
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
  "$ROOT/.claude/scripts/staged-check" src/example.py
  git reset -q

  # Test 2: staged-check fails with extra staged path
  mkdir -p src
  echo "content" > src/example.py
  echo "extra" > src/extra.py
  git add src/example.py src/extra.py
  ! "$ROOT/.claude/scripts/staged-check" src/example.py 2>/dev/null
  git reset -q

  # Test 3: staged-check rejects protected paths via protect-local
  mkdir -p config
  echo "protected" > config/local.toml
  git add config/local.toml
  ! "$ROOT/.claude/scripts/staged-check" config/local.toml 2>/dev/null
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
  ! "$ROOT/.claude/scripts/staged-check" src/example.py 2>/dev/null
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
  output=$("$ROOT/.claude/scripts/handoff")
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

  diff_line=$("$ROOT/.claude/scripts/handoff" | grep '^Diff:')
  printf '%s\n' "$diff_line" | grep -q "insertion"
  printf '%s\n' "$diff_line" | grep -q "file"
)

# Test skill structure and content
for skill in task implement qa runtime-proof sqlite-change native-analysis ship
do
  skill_file="$ROOT/.claude/skills/$skill/SKILL.md"
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

  # Codex-specific references must not survive the port
  ! grep -q "AGENTS.md" "$skill_file"
  ! grep -q "\.codex/scripts/" "$skill_file"
  ! grep -q "codex features list" "$skill_file"
done

# Verify root CLAUDE.md names all seven skills in the Skill routing section
# (backticked, as they appear there) rather than merely containing common
# English words that would pass even if no skill were actually named.
grep -q '`task`' "$CLAUDE_MD"
grep -q '`implement`' "$CLAUDE_MD"
grep -q '`qa`' "$CLAUDE_MD"
grep -q '`runtime-proof`' "$CLAUDE_MD"
grep -q '`sqlite-change`' "$CLAUDE_MD"
grep -q '`native-analysis`' "$CLAUDE_MD"
grep -q '`ship`' "$CLAUDE_MD"

# Test .claude/settings.json hooks configuration
settings_file="$ROOT/.claude/settings.json"
test -f "$settings_file"

# Test 1: JSON validity
python3 -m json.tool "$settings_file" >/dev/null

# Test 2: structural validation of the hooks key — each event must be an
# ARRAY of hook groups, and each group must carry both "matcher" and "hooks".
python3 - "$settings_file" <<'PYEOF'
import json
import sys

path = sys.argv[1]
with open(path) as fh:
    data = json.load(fh)

hooks = data.get("hooks")
if not isinstance(hooks, dict):
    sys.exit("settings.json: 'hooks' key missing or not an object")

for event in ("UserPromptSubmit", "Stop"):
    groups = hooks.get(event)
    if not isinstance(groups, list) or not groups:
        sys.exit("settings.json: hooks.%s must be a non-empty array" % event)
    for group in groups:
        if not isinstance(group, dict):
            sys.exit("settings.json: hooks.%s group must be an object" % event)
        if "matcher" not in group:
            sys.exit("settings.json: hooks.%s group missing 'matcher'" % event)
        if not isinstance(group.get("hooks"), list) or not group["hooks"]:
            sys.exit("settings.json: hooks.%s group missing non-empty 'hooks' array" % event)
        for h in group["hooks"]:
            if not isinstance(h, dict) or "type" not in h or "command" not in h:
                sys.exit("settings.json: hooks.%s hook entry missing type/command" % event)
PYEOF

# Test 3: UserPromptSubmit has conditional codegraph prompt-hook
grep -q "UserPromptSubmit" "$settings_file"
grep -q "codegraph prompt-hook" "$settings_file"
grep -q "if command -v codegraph" "$settings_file"

# Test 4: Stop has protect-local --staged
grep -q "Stop" "$settings_file"
grep -q "protect-local --staged" "$settings_file"

# Test 5: No PreToolUse hook anywhere in settings.json
! grep -q "PreToolUse" "$settings_file"

# Test 6: No destructive Git commands (commit, push, checkout, reset, clean)
! grep -q "git commit" "$settings_file"
! grep -q "git push" "$settings_file"
! grep -q "git checkout" "$settings_file"
! grep -q "git reset" "$settings_file"
! grep -q "git clean" "$settings_file"

# Test 7: No cleanup or full-QA commands
! grep -qE "cleanup|full-qa|full_qa|teardown" "$settings_file"
