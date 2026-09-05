"""SQLite database boundary for the catalog."""

import fcntl
import os
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from dj_digger.catalog.migrations import migrate


class Database:
    """A SQLite catalog connection with catalog-wide settings."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @classmethod
    def open(cls, path: Path) -> Self:
        """Open a configured catalog database."""
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=5.0)
        cls._configure_database(connection)
        cls._configure_connection(connection)
        return cls(connection)

    @staticmethod
    def _configure_database(connection: sqlite3.Connection) -> None:
        """Configure settings persisted by the database file."""
        mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            connection.close()
            raise RuntimeError(f"SQLite refused WAL mode: {mode}")

    @staticmethod
    def _configure_connection(connection: sqlite3.Connection) -> None:
        """Configure settings local to one SQLite connection."""
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 5000")

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def migrate(self) -> None:
        """Bring the catalog schema to its latest supported version."""
        migrate(self._connection)

    def scalar(self, query: str, parameters: Sequence[Any] = ()) -> Any:
        """Return the first value from a read query, or ``None`` when empty."""
        row = self._connection.execute(query, parameters).fetchone()
        return None if row is None else row[0]

    def table_exists(self, name: str) -> bool:
        """Return whether a SQLite table exists."""
        return bool(
            self.scalar("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,))
        )

    def execute(self, query: str, parameters: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Execute repository-owned SQL."""
        return self._connection.execute(query, parameters)

    def commit(self) -> None:
        """Commit a repository operation."""
        self._connection.commit()

    def optimize(self) -> None:
        """Let SQLite update planner statistics when useful."""
        self.execute("PRAGMA optimize")

    def quick_check(self) -> str:
        """Return SQLite's lightweight consistency-check result."""
        return str(self.scalar("PRAGMA quick_check"))

    def integrity_check(self) -> list[str]:
        """Return every result from SQLite's explicit full integrity check."""
        return [str(row[0]) for row in self.execute("PRAGMA integrity_check").fetchall()]

    def diagnostics(self) -> dict[str, str | int | bool]:
        """Report read-only runtime and file health details for the main database."""
        database_path = self._main_database_path()
        wal_path = database_path.with_name(f"{database_path.name}-wal")
        shm_path = database_path.with_name(f"{database_path.name}-shm")
        return {
            "path": str(database_path),
            "sqlite_version": sqlite3.sqlite_version,
            "schema_version": int(self.scalar("PRAGMA user_version") or 0),
            "journal_mode": str(self.scalar("PRAGMA journal_mode")).lower(),
            "foreign_keys": int(self.scalar("PRAGMA foreign_keys") or 0),
            "synchronous": int(self.scalar("PRAGMA synchronous") or 0),
            "busy_timeout_ms": int(self.scalar("PRAGMA busy_timeout") or 0),
            "file_size_bytes": database_path.stat().st_size if database_path.is_file() else 0,
            "wal_size_bytes": wal_path.stat().st_size if wal_path.is_file() else 0,
            "shm_present": shm_path.is_file(),
            "page_count": int(self.scalar("PRAGMA page_count") or 0),
            "page_size_bytes": int(self.scalar("PRAGMA page_size") or 0),
            "freelist_count": int(self.scalar("PRAGMA freelist_count") or 0),
            "quick_check": self.quick_check(),
        }

    def _main_database_path(self) -> Path:
        database_file = next(
            (
                filename
                for _, schema, filename in self.execute("PRAGMA database_list")
                if schema == "main" and filename
            ),
            None,
        )
        if database_file is None:
            raise RuntimeError("database diagnostics require a file-backed SQLite database")
        return Path(str(database_file)).resolve()

    @contextmanager
    def advisory_lock(self, name: str) -> Iterator[None]:
        """Hold a non-blocking process lock associated with the main database."""
        try:
            database_path = self._main_database_path()
        except RuntimeError as error:
            raise RuntimeError("advisory locks require a file-backed SQLite database") from error
        lock_path = database_path.with_name(f"{database_path.name}.{name}.lock")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError(f"advisory lock {name!r} is already held") from error
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Execute a group of catalog mutations atomically."""
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    @contextmanager
    def read_transaction(self) -> Iterator[None]:
        """Keep related export queries on one consistent SQLite snapshot."""
        self._connection.execute("BEGIN")
        try:
            yield
        finally:
            self._connection.rollback()
