# Claude Code development harness

Mirror of the Codex harness (`.codex/`) for Claude Code: skills, hooks, and
rules (CLAUDE.md), reusing the existing tool-agnostic scripts in
`.codex/scripts/` rather than duplicating them.

Spec authority: `docs/superpowers/specs/2026-08-27-codex-development-harness-design.md`
(same invariants apply — protected paths, no auto-commits, observable proof,
risk-based QA — only the harness surface changes from Codex conventions to
Claude Code conventions).

## Global Constraints

- Scripts in `.codex/scripts/` are tool-agnostic (pure POSIX sh, git-based).
  Do not fork or duplicate their logic — `.claude/scripts/` must reuse them
  via relative symlinks (`.claude/scripts/<name>` -> `../../.codex/scripts/<name>`).
- Claude Code hook config lives in `.claude/settings.json` under a `hooks`
  key (not a standalone file like Codex's `.codex/hooks.json`). Each hook
  group needs a `matcher` field (use `"*"` where Codex's config had none).
- Model table in every CLAUDE.md file must reflect the actual roles used in
  this repo: Sonnet (medium) for architecture/supervision/final review,
  Haiku for research and simple bounded implementation, Sonnet (low effort,
  when available) for complex multi-file implementation or independent risk
  review. No GPT-5.6 Sol/Luna references — those are Codex-only.
- Every SKILL.md ported from `.codex/skills/` must have Codex-specific
  mentions replaced: `AGENTS.md` -> `CLAUDE.md`, `.codex/scripts/` ->
  `.claude/scripts/`, `codex features list` / Codex CLI invocation notes
  removed or replaced with Claude Code equivalents (slash-command
  invocation, `.claude/settings.json` hooks). Do not invent new Claude-only
  behavior beyond what the Codex skill already specifies — this is a port,
  not a redesign.
- `.claude/tests/test-harness.sh` must be a real, runnable POSIX sh suite
  (mirroring `.codex/tests/test-harness.sh`'s assertions) — not a stub.
- Every `mktemp -d` test block must be wrapped in a subshell `( ... )` to
  avoid leaking cwd into later-appended sections (lesson from the Codex
  harness build — recurred once there, must not recur here).

## Task 1: `.claude/scripts/` — symlink to the existing Codex scripts

Create `.claude/scripts/` containing one relative symlink per file currently
in `.codex/scripts/` (`changed-files`, `handoff`, `package-check`,
`project-env`, `protect-local`, `qa-run`, `qa-select`, `staged-check`),
each pointing at `../../.codex/scripts/<name>`. Verify each symlink
resolves and each script still runs from the repo root when invoked as
`.claude/scripts/<name>` (e.g. `.claude/scripts/qa-select` accepts stdin
the same way `.codex/scripts/qa-select` does — run a quick smoke check
piping one path through it).

Do not copy script content. Do not modify `.codex/scripts/`.

## Task 2: `.claude/settings.json` — hooks

Create `.claude/settings.json` with a `hooks` key equivalent to
`.codex/hooks.json`'s two hooks, translated to Claude Code's schema
(`matcher` required per hook group; use `"*"`):

- `UserPromptSubmit`: command hook running
  `if command -v codegraph >/dev/null 2>&1; then exec codegraph prompt-hook; fi`
- `Stop`: command hook running `.claude/scripts/protect-local --staged`

If `.claude/settings.json` does not exist yet, create it with only the
`hooks` key. If it already exists, merge in the `hooks` key without
disturbing any other existing keys (check first).

## Task 3: Root `CLAUDE.md`

Port `AGENTS.md` (repo root) to `CLAUDE.md`, keeping the same ten sections
(Mission and architecture, Instruction scope, Exploration order, Permanent
invariants, Models and delegation, Observable proof, Risk-based QA, Git and
privacy, Skill routing, Completion report) and the same content and
invariants, with these adaptations:

- "Models and delegation" table and prose: replace the GPT-5.6 Sol/Luna
  routing with the Claude roles from Global Constraints above.
- "Instruction scope": scoped file references become `CLAUDE.md` instead of
  `AGENTS.md` (see Task 4 for the exact scoped paths — same eight
  directories as the Codex harness).
- "Skill routing": skill names stay the same (`task`, `implement`, `qa`,
  `runtime-proof`, `sqlite-change`, `native-analysis`, `ship`) but now refer
  to `.claude/skills/<name>/SKILL.md`, invoked as Claude Code slash
  commands (`/task`, `/implement`, etc.) rather than Codex's mechanism.
  Script references become `.claude/scripts/...`.
- "Completion report": still `.claude/scripts/handoff`'s six fields (Status,
  Branch, Diff, QA, Next, Risk) — identical contract, just the path prefix
  changes.
- Everything else (permanent invariants, exploration order, observable
  proof, risk-based QA profiles, git and privacy) is unchanged in substance
  — only path/tool references change.

## Task 4: Eight scoped `CLAUDE.md` files

Port the eight scoped `AGENTS.md` files to `CLAUDE.md` in the same
directories: `src/dj_digger/AGENTS.md`, `src/dj_digger/catalog/AGENTS.md`,
`src/dj_digger/analysis/AGENTS.md`, `src/dj_digger/exports/AGENTS.md`,
`tests/AGENTS.md`, `scripts/AGENTS.md`, `skills/AGENTS.md`,
`docs/AGENTS.md`. Same content and per-directory invariants; only
Codex-specific references change (script paths to `.claude/scripts/`, skill
invocation phrasing to Claude Code slash commands, any GPT-5.6 model
mentions to the Claude roles from Global Constraints). Do not rename or
restructure sections — this is a one-for-one port per file, batched as one
dispatch since all eight follow the same transformation.

## Task 5: Seven `.claude/skills/<name>/SKILL.md` files

Port all seven Codex skills to Claude Code SKILL.md format (same
`name`/`description` YAML frontmatter convention — already compatible) at
`.claude/skills/task/SKILL.md`, `.claude/skills/implement/SKILL.md`,
`.claude/skills/qa/SKILL.md`, `.claude/skills/runtime-proof/SKILL.md`,
`.claude/skills/sqlite-change/SKILL.md`, `.claude/skills/native-analysis/SKILL.md`,
`.claude/skills/ship/SKILL.md`, from `.codex/skills/<name>/SKILL.md`.

Per skill: keep the same procedural content and invariants; replace every
`AGENTS.md` reference with `CLAUDE.md`, every `.codex/scripts/` reference
with `.claude/scripts/`, and any Codex-CLI-specific invocation notes (e.g.
`codex features list`) with the Claude Code equivalent or remove if it has
no equivalent. Do not restate the model-routing table or the completion
report format inline (both skills already exist in the Codex source without
that duplication — preserve that; if you find either duplicated in the
Codex source, drop it here too, pointing to `CLAUDE.md` instead).

## Task 6: `.claude/tests/test-harness.sh`

Port `.codex/tests/test-harness.sh` to `.claude/tests/test-harness.sh`,
adjusting every path assertion from the `.codex/` tree to the `.claude/`
tree (`CLAUDE.md` existence and section checks, `.claude/settings.json`
hooks structure, `.claude/skills/*/SKILL.md` existence, `.claude/scripts/*`
symlinks resolving and being executable). Reuse the same assertion
patterns and the same subshell-isolation discipline for any `mktemp -d`
block. The suite must be runnable standalone (`sh .claude/tests/test-harness.sh`)
and exit 0 on a correct harness, non-zero with a clear message on any
missing or malformed piece.

## Task 7: Python LSP server for Claude Code

Add a Python LSP server for this project for Claude Code, so Claude's
native `LSP` tool can query it. Before writing any config: dispatch a
Haiku research pass (context7 + Claude Code docs) to confirm (a) whether
Claude Code has a native/official `.claude/settings.json` field or plugin
for declaring a project LSP server, and its exact schema, or (b) failing
that, which maintained Python LSP server to standardize on (pyright /
basedpyright / python-lsp-server) and how Claude Code's `LSP` tool expects
it to be launched. Do not guess a JSON schema — verify it. Then, in a
follow-up implementation task (Sonnet, since it requires integration
judgment): add the server declaration, using `uv tool install` or an
already-available project dependency to provide the LSP binary rather than
inventing a new global install step, and document its use in the root
`CLAUDE.md` "Exploration order" or a new short subsection, without
duplicating content already covered elsewhere.

## Acceptance

- `sh .claude/tests/test-harness.sh` passes.
- `.codex/tests/test-harness.sh` still passes unmodified (no regression to
  the existing Codex harness from the added symlinks or settings.json).
- No private library facts, no changes to `config/local.toml`, `workspace/`,
  `sets/`, or any `.sqlite*` file.
- Task 7's LSP config matches Claude Code's actual documented mechanism —
  not a guessed schema.
