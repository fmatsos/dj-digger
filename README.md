# DJ Digger — Unified V1A/V1B implementation planning bundle (revision 2)

This bundle supersedes `dj-digger-implementation-plan-v1.zip`.

The `v2` in the archive name means **planning bundle revision 2**. The implemented product scope is still **DJ Digger V1A/V1B**. Audio fingerprinting, move/rename reconciliation and duplicate detection remain future functional V2 work.

## Read order

1. `docs/superpowers/specs/2026-08-24-dj-digger-unified-v1-design.md`
2. `docs/superpowers/plans/2026-08-24-dj-digger-unified-v1-master.md`
3. `docs/superpowers/plans/2026-08-24-dj-digger-catalog-v1a.md`
4. `docs/superpowers/plans/2026-08-24-dj-digger-analysis-v1a.md`
5. `docs/superpowers/plans/2026-08-24-electronic-dj-set-curator-v1a-v1b.md`
6. `docs/superpowers/plans/2026-08-24-dj-digger-integration-v1a-v1b.md`

`docs/migrations/` explains the contract changes from the previous plan. `references/export-music-audit.sh` is included only as a parity reference and is not part of the target runtime architecture.

## Canonical target

```text
configured sources -> SQLite catalog -> regenerable facets -> set curator
```

`tracks.tsv` is created in V1A and becomes the supported first-party availability contract in V1B. Compatibility facets remain optional after cut-over.
