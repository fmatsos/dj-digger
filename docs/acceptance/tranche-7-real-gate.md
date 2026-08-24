# Tranche 7 real acceptance gate

The automated gate is `tests/integration/test_tranche7_acceptance.py`.

The real V1A test uses the production `WorkspaceApplication` composition and
only skips when ExifTool, FFmpeg/ffprobe, or the DSP dependency is unavailable.
It creates audio with FFmpeg, reads tags through ExifTool, analyzes through the
composite extractor, verifies second-run reuse, exports, and validates the
snapshot manifest.

The CIFS pilot is manual and bounded by `scripts/acceptance_cifs_pilot.py`.
Set `DJ_DIGGER_CIFS_LIBRARY` to the native read-only mount. The pilot emits
aggregate evidence only and never prints the mount path or local filenames.
With no variable it exits successfully with a JSON `skipped` status; this is
intentional for CI. With a mount it stages at most nine read-only symlinks plus
one deliberately invalid audio file outside the source, then executes the
full CLI path and requires a real partial analysis with exit code `2`, followed
by reuse on the second analysis. A mount is accepted only when `statvfs` proves
the `ST_RDONLY` flag; otherwise the gate is blocked.

The curator gate validates all three reconstructed outputs and feeds its M3U8
to `references/copy-set.sh` in a temporary destination, checking relative
paths, file count, byte integrity, and source immutability.

The V1B gate uses no recorded evaluator case as input. When the real
dependencies are installed it generates a short FFmpeg WAV, runs the default
`WorkspaceApplication.refresh()` with `legacy_compatibility = false`, and
passes the resulting `tracks.tsv` plus the three analysis facets to the
facts-only acceptance adapter. The emitted JSON is validated against the
current set schema; track identity and playlist paths must match the tracks
facet exactly, the Markdown must be non-empty, and the output directory must
contain exactly the JSON, M3U8, and Markdown artifacts.

The CIFS report accepts only a proven read-only mount whose source fingerprint
is unchanged, with successful scan, metadata, export, archived snapshot, and
both analysis runs reporting `partial` and exit code 2. The second analysis
must report reuse. Its report contains aggregate booleans only (including
`archive_created`), never mount paths or local filenames.
