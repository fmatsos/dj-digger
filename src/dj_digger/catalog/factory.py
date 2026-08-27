"""Factory for independently configured catalog connections."""

from pathlib import Path

from dj_digger.catalog.database import Database


class DatabaseFactory:
    """Open catalog database connections bound to one path."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def open(self) -> Database:
        return Database.open(self._path)
