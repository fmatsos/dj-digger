# Unified V1 Definition-of-Done Coverage

This checklist maps the approved design's 19 V1 definition-of-done items to implementation tasks.

| # | Requirement | Planned coverage |
|---|---|---|
| 1 | `export-music-audit.sh` no longer operationally required | Catalog Tasks 3, 5–9; Integration Tasks 1–2 |
| 2 | DJ Digger discovers configured libraries itself | Catalog Tasks 1, 3, 4 |
| 3 | One canonical SQLite DB for N sources | Catalog Tasks 1–2 |
| 4 | Exports are projections, never authorities | Catalog Tasks 6–9; Analysis Task 7 |
| 5 | Missing tracks retained historically | Catalog Tasks 2, 4 |
| 6 | Only successful complete scan marks missing | Catalog Task 4; Integration Task 3 |
| 7 | Missing tracks may be restored | Catalog Task 4; Integration Task 3 |
| 8 | Source media remain read-only | Catalog Tasks 1, 3, 5; Analysis Task 2; Integration Task 7 |
| 9 | Historical audit coverage incl. empty dirs/DJ metadata | Catalog Tasks 3, 7; Integration Tasks 1–2 |
| 10 | Timestamped `.tar.gz` snapshot | Catalog Task 8; Integration Task 4 |
| 11 | Existing DSP/structural coverage | Analysis Tasks 2–5 |
| 12 | Incrementality from catalog facts, no pruned cache | Analysis Tasks 1, 6, 8 |
| 13 | `tracks.tsv` in V1A with exact path + source ID | Catalog Task 6 |
| 14 | V1A legacy inventories available | Catalog Task 7 |
| 15 | V1B migrates first-party inventory consumers | Curator Tasks 4, 6; Integration Task 6 |
| 16 | Set paths remain compatible with copy workflow | Curator Task 5; Integration Task 7 |
| 17 | Structured exports versioned/validated/atomic | Catalog Tasks 6, 8; Analysis Task 7 |
| 18 | Technical uncertainty/failures surfaced | Metadata Task 5; Analysis Tasks 5–8; Curator constraints |
| 19 | V2 fingerprint/move/duplicate can be added without path PK | Catalog Task 2 + internal immutable `track_id` model |

No future functional V2 feature is implemented by these plans.
