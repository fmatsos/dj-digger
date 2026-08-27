# Catalog Layer Instructions

This scope covers the SQLite catalog schema, migrations, and transactional mutations.

## SQLite V7 as the system boundary

The catalog is the source of truth for all canonical facts: track identity,
source location, import timestamps, and analysis status. The catalog defines
the canonical schema version and enforces all invariants through foreign keys.

Facts stored in the catalog are append-only and immutable. Projections (views,
computed tables) are rebuildable from the append-only facts.

## Transactional mutations

All catalog mutations are transactional. A mutation either completes atomically
or leaves the catalog unchanged. Partial updates are forbidden.

begin-immediate transactions are required for this scope to support concurrent
reader processes while current_track_analysis, BEGIN IMMEDIATE begins the
transaction chain. A writer must observe consistent state through all mutation
steps.

## Migrations

Schema migrations are atomic and reversible. A migration target version is
adopted fully or reverted entirely. Migration scripts are testable and
deterministic.

Foreign-key validation is enforced at all times.

## Concurrency

Multiple reader processes may access the catalog simultaneously.
One writer process operates at a time. Reader and writer processes coordinate
through SQLite's locking and journal mechanisms.

The wheel package must not depend on the source checkout. Schema and migrations
ship as packaged resources.
