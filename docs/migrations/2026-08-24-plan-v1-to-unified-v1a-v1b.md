# Planning Bundle V1 → Unified V1A/V1B Migration Notes

This document explains why the previous implementation plans are not carried forward verbatim.

## Removed assumptions

- `djing-files.tsv` is no longer an internal authority; SQLite is canonical.
- `dj-audio-analyzer` is no longer a separately deployed product.
- SQLite is not a disposable cache and there is no destructive `prune()` workflow.
- The analyzer no longer accepts `--inventory` or `--no-prune`.
- The product is not limited to hard-coded `djing` and `music` roots; sources are configured and identified by stable `source_id`.

## Preserved behavior

- All meaningful historical audit outputs remain available as projections.
- Source media stay read-only.
- Existing DSP, structural section and transition-curation requirements remain.
- `copy-set.sh` remains external and continues to consume exact relative M3U8 paths.

## Schema migrations

- `dj-analysis.tsv`: analysis schema `1 → 2`; adds required `source_id`, `track_id`.
- `dj-sections.jsonl`: analysis schema `1 → 2`; adds required `source_id`, `track_id`.
- `dj-analysis-run.json`: replaces cache vocabulary (`cached`, `pruned`) with catalog vocabulary (`reused`) and adds catalog schema identity.
- `.set.json`: set schema `1 → 2`; selected tracks and alternatives require `source_id`, `track_id`.
- New `tracks.tsv` schema version `1`.
- New `library-artifacts.tsv` schema version `1`.
- New snapshot manifest schema version `1`.

The archive filename uses `v2` only to identify the second planning bundle revision. It does **not** include future functional V2 fingerprinting/move/duplicate features.
