# Export Layer Instructions

This scope covers export formats, publication, and versioning.

## Consistent snapshots

All exports in one run are produced from a single SQLite catalog snapshot.
Reads from the catalog are performed through a single transaction or connection
to ensure consistency. Partial or stale exports are never published.

## Schema validation

Export schemas are defined and validated before publication. Schema changes are
breaking and must bump the export version. All published exports conform to
their declared schema.

## Staging and atomic replacement

Exports are written to a staging area first. Once all exports for a run are
valid and complete, they are moved into production atomically.

The atomic replacement, one SQLite snapshot principle ensures that:
- An export consumer never observes partial data from a failed run
- All exports in a publication reflect a consistent catalog state
- Atomic rename operations (or similar) swap staged exports into production

## Identities and facets

Each exported fact is tagged with exact identities: `(source_id, track_id,
path)`. Analysis facets are indivisible units: all analysis results for a
track are published together, or none are.

one SQLite snapshot is read at the start of the export run. All facets
reference that same snapshot version.

## Versioning

Export versions are tracked and incremented when schemas change or when result
formats evolve. Backward compatibility is preferred; breaking changes are
documented.
