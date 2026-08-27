"""Strict initialization and ordered upgrades of the SQLite catalog schema."""

import sqlite3
from importlib.resources import files

CURRENT_VERSION = 7
CURRENT_SCHEMA = "catalog-v7.sql"
MIGRATIONS = {6: "migrate-v6-to-v7.sql"}


def migrate(connection: sqlite3.Connection) -> None:
    """Initialize a fresh catalog or upgrade a supported catalog in place."""
    current = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current == CURRENT_VERSION:
        return
    if current == 0:
        _initialize_fresh(connection)
        return
    if current > CURRENT_VERSION:
        raise RuntimeError(
            f"legacy catalog version {current} is unsupported; recreate the catalog"
        )

    while current < CURRENT_VERSION:
        filename = MIGRATIONS.get(current)
        if filename is None:
            raise RuntimeError(
                f"legacy catalog version {current} is unsupported; recreate the catalog"
            )
        _run_migration(connection, current, current + 1, filename)
        current += 1


def _initialize_fresh(connection: sqlite3.Connection) -> None:
    _run_script_transaction(
        connection,
        expected_version=0,
        target_version=CURRENT_VERSION,
        filename=CURRENT_SCHEMA,
        require_empty=True,
    )


def _run_migration(
    connection: sqlite3.Connection, from_version: int, to_version: int, filename: str
) -> None:
    _run_script_transaction(
        connection,
        expected_version=from_version,
        target_version=to_version,
        filename=filename,
        require_empty=False,
    )


def _run_script_transaction(
    connection: sqlite3.Connection,
    *,
    expected_version: int,
    target_version: int,
    filename: str,
    require_empty: bool,
) -> None:
    script = _load_sql(filename)
    try:
        connection.execute("BEGIN IMMEDIATE")
        actual_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if actual_version != expected_version:
            raise RuntimeError(
                f"catalog version changed during migration: expected {expected_version}, "
                f"found {actual_version}"
            )
        if require_empty:
            existing_objects = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
            ).fetchone()
            if existing_objects is not None:
                raise RuntimeError(
                    "unversioned nonempty catalog is unsupported; recreate the catalog"
                )
        _execute_script(connection, script)
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) != expected_version:
            raise RuntimeError("migration script changed user_version unexpectedly")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"foreign key check failed during migration: {violations!r}")
        connection.execute(f"PRAGMA user_version = {target_version}")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def _execute_script(connection: sqlite3.Connection, script: str) -> None:
    """Execute a packaged SQL script without sqlite3.executescript's implicit commit."""
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ""
    if statement.strip():
        raise RuntimeError("incomplete SQL statement in packaged migration script")


def _load_sql(filename: str) -> str:
    return (files("dj_digger.catalog") / "sql" / filename).read_text(encoding="utf-8")
