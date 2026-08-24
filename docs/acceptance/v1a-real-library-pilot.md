# V1A controlled real-library pilot — PARTIALLY BLOCKED

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
| `doctor` after extractor installation | 0 | Workspace, schema migrations, and required binary check succeeded. |
| First bounded `scan --source djing` | 124 | The initial 25-second trial timed out without output. Its temporary catalog was not reused. |
| Fresh-catalog `scan --source djing` | 0 | Completed within the five-minute cap; 366 tracks were catalogued. |
| V1A `refresh` | 124 | Reached the five-minute cap with no command output. No metadata or analysis rows were persisted. |
| Archived `snapshot` | Not run | Dependent on a completed V1A pipeline; no snapshot hash could be validated. |
| Historical/reference facet comparison | Not run | The reference script requires two library roots and would scan a second root, outside this pilot's source boundary. |

## Aggregate catalog state

| Metric | Count/status |
| --- | ---: |
| Present tracks | 366 |
| Missing tracks | 0 |
| Metadata failures | 0 persisted; refresh did not complete |
| Analysis eligibility | 0 (explicitly disabled) |
| Analysis reuse | 0 (explicitly disabled) |
| Analysis failures | 0 persisted |
| Export artifacts | 0 |
| Snapshot hash validation | Not available |

## Conclusion

**PARTIALLY BLOCKED.** The controlled scan was successful and the source remained unchanged according to the pre/post read-only manifest check. Full V1A acceptance is still blocked because `refresh` did not complete within the bounded five-minute run; consequently no canonical exports, archived snapshot, snapshot integrity validation, or reference-compatible facet comparison was produced. A follow-up should diagnose the refresh duration on this GVFS-backed source while retaining the same source boundary and isolation rules.
