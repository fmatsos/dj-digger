# Curator source contracts

V1B availability is explicitly sourced from `tracks.tsv`. A candidate must be
a member of that export and have `set_eligible=true` before it enters
optimization. Analysis never makes an unavailable track available.

Track facts are source-aware and identify every track by `source_id`, `track_id`,
and the source-relative exact path from `tracks.tsv`. Curator consumers must use
those identities rather than a path alone.

Analysis can be absent or marked `partial`; this is an explicit uncertainty, not
permission to invent BPM, key, duration, sections, or compatibility. A missing
join remains unavailable for technical claims while the availability decision
still comes only from `tracks.tsv`.

Reject a path that resolves to zero or more than one selected source-aware
identity. Never infer availability from web results, a directory name, or model
knowledge.

When artifacts overlap, resolve contracts in this exact order:

1. `tracks.tsv` — current availability + `source_id` + `set_eligible` + exact path
2. `dj-analysis.tsv` — track/global/window technical facts
3. `dj-sections.jsonl` — structural facts
4. `dj-analysis-run.json` — audit/staleness signal
5. external context — classification/context only, never availability
