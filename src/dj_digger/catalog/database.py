"""SQLite database boundary for the catalog."""

import sqlite3
from collections.abc import Sequence
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
