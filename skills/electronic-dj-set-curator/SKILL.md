# Electronic DJ set curator

## V1B source contract

Use `tracks.tsv` as the availability source. Before a candidate enters
optimization, require both membership in that export and `set_eligible=true`.
Preserve `source_id` and the export's exact path when joining facts and emitting
a set.

Resolve inputs in this exact order:

1. `tracks.tsv` — current availability + `source_id` + `set_eligible` + exact path
2. `dj-analysis.tsv` — track/global/window technical facts
3. `dj-sections.jsonl` — structural facts
4. `dj-analysis-run.json` — audit/staleness signal
5. external context — classification/context only, never availability
