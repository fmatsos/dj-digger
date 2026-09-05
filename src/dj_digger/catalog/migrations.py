"""Strict initialization and ordered upgrades of the SQLite catalog schema."""

import sqlite3
from importlib.resources import files

from sqlite_utils import Database
from sqlite_utils.migrations import Migrations

CURRENT_VERSION = 9
CURRENT_SCHEMA = "catalog-v9.sql"
MIGRATIONS = Migrations("dj-digger")


@MIGRATIONS()
def dj_digger_000_initialize_v9(database: Database) -> None:
    """Initialize an empty catalog directly at the current schema."""
    connection = database.conn
    if _version(connection) == 0:
        _run_script_transaction(
            connection,
            expected_version=0,
            target_version=CURRENT_VERSION,
            filename=CURRENT_SCHEMA,
            require_empty=True,
        )


@MIGRATIONS()
def dj_digger_006_to_007(database: Database) -> None:
    """Upgrade a V6 catalog to V7."""
    _upgrade_if_current(database.conn, 6, "migrate-v6-to-v7.sql")


@MIGRATIONS()
def dj_digger_007_to_008(database: Database) -> None:
    """Upgrade a V7 catalog to V8."""
    _upgrade_if_current(database.conn, 7, "migrate-v7-to-v8.sql")


@MIGRATIONS()
def dj_digger_008_to_009(database: Database) -> None:
    """Upgrade a V8 catalog to V9."""
    _upgrade_if_current(database.conn, 8, "migrate-v8-to-v9.sql")


def migrate(connection: sqlite3.Connection) -> None:
    """Initialize or upgrade a catalog using the sqlite-utils migration registry."""
    current = _version(connection)
    if current > CURRENT_VERSION:
        raise RuntimeError(f"legacy catalog version {current} is unsupported; recreate the catalog")
    if 0 < current < 6:
        raise RuntimeError(f"legacy catalog version {current} is unsupported; recreate the catalog")
    MIGRATIONS.apply(Database(connection))


def _upgrade_if_current(connection: sqlite3.Connection, from_version: int, filename: str) -> None:
    if _version(connection) == from_version:
        _run_script_transaction(
            connection,
            expected_version=from_version,
            target_version=from_version + 1,
            filename=filename,
            require_empty=False,
        )


def _version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


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
                "SELECT 1 FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' AND name != '_sqlite_utils_migrations' LIMIT 1"
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
    resource = files("dj_digger.catalog").joinpath("sql", filename)
    if not resource.is_file():
        raise FileNotFoundError(
            f"required packaged resource missing: dj_digger.catalog/sql/{filename}"
        )
    return resource.read_text(encoding="utf-8")
