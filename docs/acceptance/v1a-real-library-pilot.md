# V1A controlled real-library pilot — ACCEPTED WITH ANALYSIS EXCLUDED

## Scope and isolation

- Source: controlled DJ library (one configured `djing` source only).
- All database, export, configuration, cache, logs, and snapshot candidates were isolated in a temporary workspace outside the source.
- The source was inspected read-only. Its initial and final regular-file counts were both **521**.
- Integrity check: a streaming SHA-256 was calculated over a sorted manifest of each source-relative path, byte size, and nanosecond mtime. The initial and final fingerprints matched. The checksum itself is intentionally omitted from this report.
- Analysis was explicitly disabled for this pilot. This avoids invoking an unconfigured analyzer and makes analysis eligibility and reuse both zero by configuration.

## Commands and evidence

| Action | Exit | Result |
| --- | ---: | --- |
| Isolated CLI availability check | 0 | CLI was runnable with its cache and tools isolated. |
| Native-mount `doctor` | 0 | Workspace, schema migrations, and required binary check succeeded. |
| Native-mount `scan --source djing` | 0 | Completed in a fresh isolated catalog; 366 tracks were catalogued. |
| V1A `refresh` | 0 | Metadata refresh and canonical/compatibility export completed. |
| Archived `snapshot` | 0 | Snapshot and archive were created in the temporary workspace. |
| Snapshot validation | 0 | Both manifest facet digests matched; all expected archive members were present. |
| Historical/reference comparison | 0 | The reference operated against the same bounded root and wrote only to the temporary workspace. |

## Aggregate catalog state

| Metric | Count/status |
| --- | ---: |
| Present tracks | 366 |
| Missing tracks | 0 |
| Metadata extracted | 366 |
| Metadata failures | 0 |
| Analysis eligibility | 0 (explicitly disabled) |
| Analysis reuse | 0 (explicitly disabled) |
| Analysis failures | 0 |
| Export artifacts | 12 |
| Snapshot hash validation | 2 manifest facets checked; 0 mismatches |
| Archive validation | 3 expected members present |
| Common inventory path-set comparison | 366 application paths; 366 reference paths; 0 differences |
| Known comparison difference | The reference format emits additional second-root-oriented artifacts by design; this pilot used the same bounded source for both reference inputs, so no broader parity claim is made. |

## Conclusion

**ACCEPTED WITH ANALYSIS EXCLUDED.** The native-mount controlled scan, metadata refresh, exports, archived snapshot, snapshot validation, and bounded reference inventory comparison all succeeded. The source remained unchanged according to the pre/post read-only manifest check. Audio analysis was intentionally outside this pilot: it had zero eligible, analyzed, reused, and failed tracks by configuration.
