import sqlite3
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.factory import DatabaseFactory


def test_open_configures_file_database_and_closes_after_context(tmp_path: Path) -> None:
    with Database.open(tmp_path / "catalog.sqlite") as database:
        assert database.scalar("PRAGMA journal_mode") == "wal"
        assert database.scalar("PRAGMA foreign_keys") == 1
        assert database.scalar("PRAGMA synchronous") == 1
        assert database.scalar("PRAGMA busy_timeout") == 5_000

    with pytest.raises(sqlite3.ProgrammingError):
        database.scalar("SELECT 1")


def test_open_uses_five_second_sqlite_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_connect = sqlite3.connect
    calls: list[tuple[Path, float]] = []

    def recording_connect(path: Path, *, timeout: float) -> sqlite3.Connection:
        calls.append((path, timeout))
        return original_connect(path, timeout=timeout)

    monkeypatch.setattr(sqlite3, "connect", recording_connect)

    with Database.open(tmp_path / "catalog.sqlite"):
        pass

    assert calls == [(tmp_path / "catalog.sqlite", 5.0)]


def test_open_read_only_refuses_a_missing_catalog(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "catalog.sqlite"

    with pytest.raises(sqlite3.OperationalError):
        Database.open_read_only(missing)

    assert not missing.parent.exists()


def test_open_read_only_enforces_query_only(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"
    with Database.open(path) as writer:
        writer.migrate()

    with Database.open_read_only(path) as reader:
        assert reader.scalar("PRAGMA query_only") == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.execute("CREATE TABLE forbidden (id INTEGER)")


def test_database_configuration_rejects_non_wal_mode_and_closes_connection() -> None:
    connection = sqlite3.connect(":memory:")

    with pytest.raises(RuntimeError, match="SQLite refused WAL mode: memory"):
        Database._configure_database(connection)

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_factory_opens_independent_connections_and_rolls_back_failed_transaction(
    tmp_path: Path,
) -> None:
    factory = DatabaseFactory(tmp_path / "catalog.sqlite")

    with factory.open() as first, factory.open() as second:
        first.execute("PRAGMA busy_timeout = 1")
        assert first.scalar("PRAGMA busy_timeout") == 1
        assert second.scalar("PRAGMA busy_timeout") == 5_000

        first.execute("CREATE TABLE pending_writes (value TEXT NOT NULL)")
        first.commit()

        assert second.scalar("SELECT count(*) FROM pending_writes") == 0

        with pytest.raises(RuntimeError, match="abort write"):
            with first.transaction():
                first.execute("INSERT INTO pending_writes VALUES ('rolled back')")
                raise RuntimeError("abort write")

        assert second.scalar("SELECT count(*) FROM pending_writes") == 0

    with pytest.raises(sqlite3.ProgrammingError):
        first.scalar("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        second.scalar("SELECT 1")
