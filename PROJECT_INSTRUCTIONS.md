# Project instructions

## Curator availability contract

The V1B curator reads current availability from `tracks.tsv`. A candidate must
be a member of that export and have `set_eligible=true` before it enters
optimization. Its identity is `source_id` plus the exact path supplied by the
export.

Resolve curator inputs in this exact order:

1. `tracks.tsv` — current availability + `source_id` + `set_eligible` + exact path
2. `dj-analysis.tsv` — track/global/window technical facts
3. `dj-sections.jsonl` — structural facts
4. `dj-analysis-run.json` — audit/staleness signal
5. external context — classification/context only, never availability
