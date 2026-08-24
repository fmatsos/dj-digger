"""Ordered SQLite catalog migrations."""

import sqlite3
from importlib.resources import files

MIGRATIONS = (
    (1, "catalog-v1.sql"),
    (2, "catalog-v2.sql"),
    (3, "catalog-v3.sql"),
    (4, "catalog-v4.sql"),
    (5, "catalog-v5.sql"),
)


def migrate(connection: sqlite3.Connection) -> None:
    """Apply every pending catalog migration atomically."""
    current = int(connection.execute("PRAGMA user_version").fetchone()[0])
    for version, filename in MIGRATIONS:
        if version <= current:
            continue
        script = _load_sql(filename)
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n" + script + f"\nPRAGMA user_version = {version};\nCOMMIT;"
            )
        except sqlite3.Error:
            connection.rollback()
            raise
        current = version


def _load_sql(filename: str) -> str:
    return (files("dj_digger.catalog") / "sql" / filename).read_text(encoding="utf-8")
