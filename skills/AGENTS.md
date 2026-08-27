# Skills Scope Instructions

This scope covers the curator workflow and set management skills.

## Export consumption

Skills consume the four exports from a single export run: the track catalog,
analysis results, metadata, and track list. All consumed exports must originate
from the same run to ensure consistency.

tracks.tsv is the availability authority: a track is considered available for
curation only if it appears in the current tracks.tsv export.

## Curator boundary

The existing curator boundary is preserved. Skills do not modify the export
pipeline or export formats. Skills operate on the published exports as-is.

## Identity preservation

Track identities from the catalog are preserved through curation. A curated set
references exact `(source_id, track_id)` pairs. Set changes do not rewrite or
modify the underlying track identities.

## Fixture prevention

tracks.tsv, same export run: all artifacts must come from the same export run
with the same timestamp and version. Skills do not replace real exports with
fixtures or synthetic data for testing. If an export is unavailable or
corrupted, the skill reports the error rather than proceeding with mock data.

## Set validation

Published set artifacts are validated before acceptance. Validation includes:
- Exact identity matching against the catalog
- Completeness (all referenced tracks exist)
- Consistency (metadata matches the exports)
- Determinism (identical inputs produce identical sets)
