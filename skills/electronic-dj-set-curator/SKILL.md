---
name: electronic-dj-set-curator
description: Use when curating an electronic DJ set from local tracks.tsv and companion DJ analysis exports, especially when narrative constraints, uncertain analysis, source identity, or set-copy artifacts matter
---

# Electronic DJ set curator

Curate only from local, source-aware exports. Keep the seven transition
strategies in the schema unchanged.

## Contract

Load inputs in this exact order:

1. `tracks.tsv` — membership, exact `path`, `source_id`, and availability.
2. `dj-analysis.tsv` — technical track/global/window facts.
3. `dj-sections.jsonl` — intro, break, drop, outro and other structural facts.
4. `dj-analysis-run.json` — run status, freshness and partial-analysis signal.

Join by `(source_id, track_id, path)` and preserve those three values verbatim.
Reject ambiguous paths, unresolved references, and mixed sources without an
explicitly resolvable common library root. A row absent from `tracks.tsv` or
with `set_eligible=false` is ineligible; never recover availability from web
search, a folder name, or model knowledge. External context is classification
only, never availability.

## Workflow

1. Parse the brief into hard constraints, a narrative trajectory, and target
   duration. Hard constraints are non-compensable.
2. Filter candidates to export membership and `set_eligible=true`; then join
   analysis and sections. Mark missing or `partial` analysis as uncertain;
   never fabricate BPM, key, duration, compatibility, or sections.
3. Build the duration-aware narrative (opening, development, peak, release)
   from facts. At every position retain exactly 3 branches and record why each
   is viable or uncertain in the Markdown sheet as `### Position N candidates`,
   followed by exactly three numbered factual/uncertain entries. End that
   section with `## Improvisation branches` and numbered branch entries.
4. Score transitions only with facts. Select only one of these schema values:
   `LONG_BLEND`, `STANDARD_BLEND`, `LATE_BASS_HANDOFF`, `SHORT_HANDOFF`,
   `STRUCTURAL_SWAP`, `BREAK_TRANSITION`, `CUT_OR_ECHO`. State the factual
   reason, confidence, regions, and unknowns; do not imply unsupported precision.
5. Choose the core, alternatives, and improvisation branches. Alternatives
   must also be eligible and source-aware. Validate identity, paths, hard
   constraints, duration, and every transition reference before emission.
6. Always write all three artifacts: `<identity>.set.json` (validated against
   the repository-declared set schema), `<identity>.m3u8` (exact relative paths
   only), and a Markdown
   transition/branch sheet. A mixed-source M3U8 requires the explicit common
   root but never writes that root into the list.

## Evidence and failure rules

Use `HIGH`, `MEDIUM`, or `LOW` confidence only as supported by exports.
Explain missing/partial analysis in validation and Markdown. Refuse rather than
guess when a path resolves to zero or multiple selected tracks, a hard
constraint cannot be proven, or a source root is ambiguous. Keep source IDs,
track IDs, and exact paths unchanged in every artifact.

Detailed candidate identity, transition evidence, path validation, and emission
pseudocode live in `references/compatibility-engine.md`,
`references/source-contracts.md`, and `references/set-emission.md`.
