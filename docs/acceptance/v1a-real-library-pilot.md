# V1A controlled real-library pilot — BLOCKED

## Scope and isolation

- Source: controlled DJ library (one configured `djing` source only).
- All database, export, configuration, cache, logs, and snapshot candidates were isolated in a temporary workspace outside the source.
- The source was inspected read-only. Its initial and final regular-file counts were both **521**.
- Integrity check: a streaming SHA-256 was calculated over a sorted manifest of each source-relative path, byte size, and nanosecond mtime. The initial and final fingerprints matched. The checksum itself is intentionally omitted from this report.

## Commands and evidence

| Action | Exit | Result |
| --- | ---: | --- |
| Isolated CLI availability check | 0 | CLI was runnable with its cache and tools isolated. |
| `doctor` | 1 | Required binary unavailable: `exiftool`. |
| `scan --source djing` | 124 | Stopped by the controlled 25-second timeout without output on the GVFS-backed source. The temporary catalog contained zero tracks afterwards. |
| V1A `refresh` | Not run | Blocked by the missing required metadata extractor; no claim of successful refresh is made. |
| Archived `snapshot` | Not run | Dependent on a completed V1A pipeline; no snapshot hash could be validated. |
| Historical/reference facet comparison | Not run | The reference script requires two library roots and would scan a second root, outside this pilot's source boundary. |

## Aggregate catalog state

| Metric | Count/status |
| --- | ---: |
| Present tracks | 0 (scan did not complete) |
| Missing tracks | 0 (scan did not complete) |
| Metadata failures | Not attempted |
| Analysis failures | Not attempted |
| Analysis reuse | Not attempted |
| Export artifacts | 0 |
| Snapshot hash validation | Not available |

## Conclusion

**BLOCKED.** The source remained unchanged according to the pre/post read-only manifest check, but this environment cannot establish V1A acceptance: the metadata extractor is absent and the configured scan did not complete within the bounded timeout on this GVFS-backed source. A rerun requires the required extractor and a supported or sufficiently responsive mounted source; only then should refresh, archived snapshot validation, and reference-compatible facet comparison be attempted.
