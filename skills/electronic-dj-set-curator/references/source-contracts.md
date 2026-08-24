# Curator source contracts

V1A set availability remains explicitly sourced from `djing-files.tsv`; analysis
does not alter that availability decision.

Analysis facts are source-aware and identify every track by the tuple
`source_id`, `track_id`, and source-relative `path`. Curator consumers must use
these identities rather than a path alone.

When artifacts overlap, resolve contracts in this order:

1. `djing-files.tsv` for V1A availability.
2. `dj-analysis.tsv` and `dj-sections.jsonl` for source-aware analysis.
3. `dj-analysis-run.json` for the analysis-run audit.
