---
name: sqlite-change
description: Validate catalog changes, migrations, rollback, constraints, and SQL packaging
---

## Purpose

Handles SQLite catalog schema, migrations, and exports. Ensures consistency, foreign-key integrity, and reversibility.

## Checks

1. **Rollback safety**: The repository's supported rollback or recovery path
   works when one is defined.
2. **Foreign keys**: pragma foreign_key_check returns no violations.
3. **Constraints**: All unique, NOT NULL, and CHECK constraints hold.
4. **Projections**: Any read models or materialized projections update correctly.
5. **Concurrency**: BEGIN IMMEDIATE transactions prevent write conflicts.
6. **Packaged SQL**: Migration SQL is in `.sql` files, not string literals.
7. **Schema metadata**: The repository's declared schema metadata remains
   consistent with the applied migration.

## Migration workflow

1. **UP**: Apply migration; verify schema and constraints.
2. **Rollback**: If reversal is supported, apply it and verify the prior schema
   is restored; otherwise verify the documented recovery path.
3. **Projection check**: Run projection queries; confirm results match expectations.
4. **Concurrency test**: Open two connections; use BEGIN IMMEDIATE; verify no write conflicts.

## Observable proof

```
Migration: <up migration artifact>
Rollback: <down migration or documented rollback procedure>
Constraints: pragma foreign_key_check (0 violations)
Projections: <query or check against the affected read model> (N rows)
Concurrency: BEGIN IMMEDIATE (no SQLITE_BUSY)
```

## Do not do

- Write schema changes as Python strings
- Skip the repository's documented rollback or recovery verification
- Ignore foreign-key violations
- Use transaction modes other than BEGIN IMMEDIATE
