"""SQLite database boundary for the catalog."""

import fcntl
import os
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dj_digger.catalog.migrations import migrate


class Database:
    """A SQLite catalog connection with catalog-wide settings."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @classmethod
    def open(cls, path: Path) -> "Database":
        """Open a catalog database and enforce foreign-key constraints."""
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys = ON")
        return cls(connection)

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
            self.scalar(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
            )
        )

    def execute(self, query: str, parameters: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Execute repository-owned SQL."""
        return self._connection.execute(query, parameters)

    def commit(self) -> None:
        """Commit a repository operation."""
        self._connection.commit()

    @contextmanager
    def advisory_lock(self, name: str) -> Iterator[None]:
        """Hold a non-blocking process lock associated with the main database."""
        database_file = next(
            (
                filename
                for _, schema, filename in self._connection.execute("PRAGMA database_list")
                if schema == "main" and filename
            ),
            None,
        )
        if database_file is None:
            raise RuntimeError("advisory locks require a file-backed SQLite database")
        database_path = Path(str(database_file)).resolve()
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
        self._connection.execute("BEGIN")
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
