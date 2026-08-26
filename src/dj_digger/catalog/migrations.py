"""Strict initialization of the current SQLite catalog schema."""

import sqlite3
from importlib.resources import files

CURRENT_VERSION = 6
CURRENT_SCHEMA = "catalog-v6.sql"


def migrate(connection: sqlite3.Connection) -> None:
    """Initialize a fresh catalog or validate an already-current one."""
    current = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current == CURRENT_VERSION:
        return
    if current != 0:
        raise RuntimeError(
            f"legacy catalog version {current} is unsupported; recreate the catalog"
        )
    existing_objects = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
    ).fetchone()
    if existing_objects is not None:
        raise RuntimeError("unversioned nonempty catalog is unsupported; recreate the catalog")
    script = _load_sql(CURRENT_SCHEMA)
    try:
        connection.executescript(
            "BEGIN IMMEDIATE;\n"
            + script
            + f"\nPRAGMA user_version = {CURRENT_VERSION};\nCOMMIT;"
        )
    except sqlite3.Error:
        connection.rollback()
        raise


def _load_sql(filename: str) -> str:
    return (files("dj_digger.catalog") / "sql" / filename).read_text(encoding="utf-8")
