---
name: sqlite-change
description: Validate catalog changes, migrations, rollback, constraints, and SQL packaging
---

## Purpose

Handles SQLite catalog schema, migrations, and exports. Ensures consistency, foreign-key integrity, and reversibility.

## Checks

1. **Rollback safety**: Migration can be reversed; DOWN path works.
2. **Foreign keys**: pragma foreign_key_check returns no violations.
3. **Constraints**: All unique, NOT NULL, and CHECK constraints hold.
4. **Projections**: V7 catalog projections (current_track_analysis, etc.) update correctly.
5. **Concurrency**: BEGIN IMMEDIATE transactions prevent write conflicts.
6. **Packaged SQL**: Migration SQL is in `.sql` files, not string literals.
7. **Version increment**: Catalog version is incremented if schema changes.

## Migration workflow

1. **UP**: Apply migration; verify schema and constraints.
2. **DOWN**: Reverse migration; verify prior schema is restored.
3. **Projection check**: Run projection queries; confirm results match expectations.
4. **Concurrency test**: Open two connections; use BEGIN IMMEDIATE; verify no write conflicts.

## Observable proof

```
Migration: catalog-vX.sql
DOWN: catalog-vX-1.sql
Constraints: pragma foreign_key_check (0 violations)
Projections: SELECT COUNT(*) FROM current_track_analysis (N rows)
Concurrency: BEGIN IMMEDIATE (no SQLITE_BUSY)
```

## Do not do

- Write schema changes as Python strings
- Skip DOWN migration
- Ignore foreign-key violations
- Use transaction modes other than BEGIN IMMEDIATE
