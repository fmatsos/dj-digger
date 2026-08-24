"""Catalog repositories that encapsulate persistence SQL."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SourceRepository:
    """Configured source roots."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def upsert(
        self, source_id: str, root_path: Path, *, set_eligible: bool, analyze: bool, enabled: bool
    ) -> None:
        """Create or update a configured source without changing its identity."""
        now = _now()
        self._database.execute(
            """
            INSERT INTO library_sources
                (source_id, root_path, set_eligible, analyze, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                root_path = excluded.root_path,
                set_eligible = excluded.set_eligible,
                analyze = excluded.analyze,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (source_id, str(root_path), set_eligible, analyze, enabled, now, now),
        )
        self._database.commit()

    def update_root(self, source_id: str, root_path: Path) -> None:
        """Relocate a configured source while retaining its source identifier."""
        self._database.execute(
            "UPDATE library_sources SET root_path = ?, updated_at = ? WHERE source_id = ?",
            (str(root_path), _now(), source_id),
        )
        self._database.commit()


class ScanRunRepository:
    """Minimal scan-run creation required by track foreign keys."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def start(self, source_id: str, *, scanner_version: str) -> int:
        """Start a scan run and return its database identity."""
        cursor = self._database.execute(
            """
            INSERT INTO scan_runs (source_id, started_at, status, scanner_version)
            VALUES (?, ?, 'running', ?)
            """,
            (source_id, _now(), scanner_version),
        )
        self._database.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a scan run id")
        return cursor.lastrowid


class TrackRepository:
    """Tracks keyed by their stable source-relative location."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def insert(
        self,
        *,
        source_id: str,
        relative_path: str,
        filename: str,
        extension: str,
        size_bytes: int,
        mtime_ns: int,
        scan_id: int,
    ) -> Track:
        """Insert a present track and return its immutable identity."""
        now = _now()
        cursor = self._database.execute(
            """
            INSERT INTO tracks (
                source_id, relative_path, filename, extension, size_bytes, mtime_ns,
                presence_status, discovered_at, last_seen_at, created_scan_id, last_seen_scan_id
            ) VALUES (?, ?, ?, ?, ?, ?, 'present', ?, ?, ?, ?)
            """,
            (
                source_id,
                relative_path,
                filename,
                extension,
                size_bytes,
                mtime_ns,
                now,
                now,
                scan_id,
                scan_id,
            ),
        )
        self._database.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a track id")
        track = self.find(source_id, relative_path)
        if track is None:
            raise RuntimeError("Inserted track could not be read")
        return track

    def find(self, source_id: str, relative_path: str) -> Track | None:
        """Find a track by its source-relative identity."""
        row = self._database.execute(
            """
            SELECT id, source_id, relative_path, filename, extension, size_bytes,
                   mtime_ns, presence_status
            FROM tracks WHERE source_id = ? AND relative_path = ?
            """,
            (source_id, relative_path),
        ).fetchone()
        return None if row is None else _track_from_row(row)

    def present_for_source(self, source_id: str) -> list[Track]:
        """List present tracks for one configured source."""
        rows = self._database.execute(
            """
            SELECT id, source_id, relative_path, filename, extension, size_bytes,
                   mtime_ns, presence_status
            FROM tracks WHERE source_id = ? AND presence_status = 'present' ORDER BY id
            """,
            (source_id,),
        ).fetchall()
        return [_track_from_row(row) for row in rows]


def _track_from_row(row: tuple[Any, ...]) -> Track:
    return Track(
        id=int(row[0]),
        source_id=str(row[1]),
        relative_path=str(row[2]),
        filename=str(row[3]),
        extension=str(row[4]),
        size_bytes=int(row[5]),
        mtime_ns=int(row[6]),
        presence_status=str(row[7]),
    )
