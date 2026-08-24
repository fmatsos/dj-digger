"""Catalog repositories that encapsulate persistence SQL."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

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

    def set_last_successful_scan(self, source_id: str, run_id: int, now: str) -> None:
        """Record the scan that last reconciled this source."""
        self._database.execute(
            "UPDATE library_sources SET last_successful_scan_id = ?, updated_at = "
            "? WHERE source_id = ?",
            (run_id, now, source_id),
        )

    def roots(self) -> dict[str, Path]:
        """Return current source roots keyed by stable source identity."""
        rows = self._database.execute("SELECT source_id, root_path FROM library_sources").fetchall()
        return {str(source_id): Path(root_path) for source_id, root_path in rows}


class ScanRunRepository:
    """Minimal scan-run creation required by track foreign keys."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def start(self, source_id: str, *, scanner_version: str) -> int:
        """Start a scan run and return its database identity."""
        with self._database.transaction():
            cursor = self._database.execute(
                """
                INSERT INTO scan_runs (source_id, started_at, status, scanner_version)
                VALUES (?, ?, 'running', ?)
                """,
                (source_id, _now(), scanner_version),
            )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a scan run id")
        return cursor.lastrowid

    def require_running(self, run_id: int) -> str:
        """Return the source for a running run, rejecting terminal or unknown runs."""
        row = self._database.execute(
            "SELECT source_id, status FROM scan_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None or row[1] != "running":
            raise ValueError("scan run must exist and be running")
        return str(row[0])

    def update_counters(
        self, run_id: int, files_seen: int, audio_seen: int, artifacts_seen: int
    ) -> None:
        """Persist counters reported by one source observation."""
        self._database.execute(
            "UPDATE scan_runs SET files_seen = ?, audio_seen = ?, artifacts_seen = ? WHERE id = ?",
            (files_seen, audio_seen, artifacts_seen, run_id),
        )

    def mark_succeeded(self, run_id: int, now: str) -> None:
        """Make a running scan terminally successful."""
        self._database.execute(
            """
            UPDATE scan_runs SET status = 'succeeded', finished_at = ?, error_stage = NULL,
                error_message = NULL WHERE id = ?
            """,
            (now, run_id),
        )

    def mark_failed(self, run_id: int, stage: str, error: str, now: str) -> None:
        """Make a running scan terminally failed without reconciliation."""
        self._database.execute(
            """
            UPDATE scan_runs SET status = 'failed', finished_at = ?, error_stage = ?,
                error_message = ? WHERE id = ?
            """,
            (now, stage, error, run_id),
        )


class TrackRepository:
    """Tracks keyed by their stable source-relative location."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def export_rows(self) -> list[tuple[Any, ...]]:
        """Return present tracks with their current public metadata projection."""
        return self._database.execute(
            """
            SELECT t.id, t.source_id, t.relative_path, t.filename, t.extension,
                   t.size_bytes, t.mtime_ns, s.set_eligible,
                   e.title, e.artist, e.album_artist, e.album, e.track_number,
                   e.disc_number, e.genre, e.date, e.year, e.composer, e.comment,
                   e.tag_bpm, e.tag_initial_key, e.grouping,
                   a.duration_seconds, a.sample_rate, a.channels, a.codec,
                   a.container, a.bitrate, a.lossless
            FROM tracks t
            JOIN library_sources s ON s.source_id = t.source_id
            LEFT JOIN embedded_metadata e ON e.track_id = t.id
            LEFT JOIN technical_audio_metadata a ON a.track_id = t.id
            WHERE t.presence_status = 'present'
            ORDER BY t.source_id, t.relative_path, t.id
            """
        ).fetchall()

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

    def observe(
        self,
        source_id: str,
        run_id: int,
        relative_path: str,
        size_bytes: int,
        mtime_ns: int,
        now: str,
    ) -> "TrackObservation":
        """Upsert one observed track and describe its lifecycle transition."""
        row = self._database.execute(
            "SELECT id, presence_status, size_bytes, mtime_ns FROM tracks "
            "WHERE source_id = ? AND relative_path = ?",
            (source_id, relative_path),
        ).fetchone()
        path = Path(relative_path)
        if row is None:
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
                    path.name,
                    path.suffix,
                    size_bytes,
                    mtime_ns,
                    now,
                    now,
                    run_id,
                    run_id,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a track id")
            return TrackObservation(
                cursor.lastrowid, discovered=True, restored=False, metadata_changed=False
            )
        track_id, presence, old_size, old_mtime = row
        self._database.execute(
            """
            UPDATE tracks SET filename = ?, extension = ?, size_bytes = ?, mtime_ns = ?,
                presence_status = 'present', last_seen_at = ?, missing_since = NULL,
                last_restored_at = CASE WHEN presence_status = 'missing' THEN ?
                    ELSE last_restored_at END,
                last_seen_scan_id = ? WHERE id = ?
            """,
            (path.name, path.suffix, size_bytes, mtime_ns, now, now, run_id, track_id),
        )
        return TrackObservation(
            track_id,
            discovered=False,
            restored=presence == "missing",
            metadata_changed=old_size != size_bytes or old_mtime != mtime_ns,
        )

    def mark_missing_not_seen(self, source_id: str, run_id: int, now: str) -> list[int]:
        """Mark only previously present tracks absent from a successful run."""
        rows = self._database.execute(
            "SELECT id FROM tracks WHERE source_id = ? AND presence_status = 'present' "
            "AND last_seen_scan_id != ?",
            (source_id, run_id),
        ).fetchall()
        self._database.execute(
            "UPDATE tracks SET presence_status = 'missing', missing_since = ? "
            "WHERE source_id = ? AND presence_status = 'present' AND last_seen_scan_id != ?",
            (now, source_id, run_id),
        )
        return [int(row[0]) for row in rows]


class DirectoryRepository:
    """Source-relative directories with a presence lifecycle."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def observe(self, source_id: str, run_id: int, relative_path: str, now: str) -> None:
        self._database.execute(
            """
            INSERT INTO directories (source_id, relative_path, presence_status, discovered_at,
                last_seen_at, missing_since, last_seen_scan_id)
            VALUES (?, ?, 'present', ?, ?, NULL, ?)
            ON CONFLICT(source_id, relative_path) DO UPDATE SET presence_status = 'present',
                last_seen_at = excluded.last_seen_at, missing_since = NULL,
                last_seen_scan_id = excluded.last_seen_scan_id
            """,
            (source_id, relative_path, now, now, run_id),
        )

    def mark_missing_not_seen(self, source_id: str, run_id: int, now: str) -> int:
        return self._database.execute(
            "UPDATE directories SET presence_status = 'missing', missing_since = ? "
            "WHERE source_id = ? AND presence_status = 'present' AND last_seen_scan_id != ?",
            (now, source_id, run_id),
        ).rowcount


class ArtifactRepository:
    """Source-relative DJ metadata artifacts with a presence lifecycle."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def observe(
        self,
        source_id: str,
        run_id: int,
        relative_path: str,
        artifact_type: str,
        size_bytes: int,
        mtime_ns: int,
        now: str,
    ) -> None:
        self._database.execute(
            """
            INSERT INTO library_artifacts (source_id, relative_path, artifact_type, size_bytes,
                mtime_ns, presence_status, first_seen_at, last_seen_at, missing_since,
                last_seen_scan_id)
            VALUES (?, ?, ?, ?, ?, 'present', ?, ?, NULL, ?)
            ON CONFLICT(source_id, relative_path) DO UPDATE SET
                artifact_type = excluded.artifact_type,
                size_bytes = excluded.size_bytes, mtime_ns = excluded.mtime_ns,
                presence_status = 'present', last_seen_at = excluded.last_seen_at,
                missing_since = NULL, last_seen_scan_id = excluded.last_seen_scan_id
            """,
            (
                source_id,
                relative_path,
                artifact_type,
                size_bytes,
                mtime_ns,
                now,
                now,
                run_id,
            ),
        )

    def mark_missing_not_seen(self, source_id: str, run_id: int, now: str) -> int:
        return self._database.execute(
            "UPDATE library_artifacts SET presence_status = 'missing', missing_since = ? "
            "WHERE source_id = ? AND presence_status = 'present' AND last_seen_scan_id != ?",
            (now, source_id, run_id),
        ).rowcount


class EventRepository:
    """Append-only track lifecycle events."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def append(
        self, track_id: int, run_id: int | None, event_type: str, payload_json: str | None, now: str
    ) -> None:
        self._database.execute(
            "INSERT INTO track_events (track_id, occurred_at, scan_run_id, event_type, "
            "payload_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (track_id, now, run_id, event_type, payload_json),
        )


class EmbeddedMetadataRepository:
    """Current normalized ExifTool-owned metadata."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def eligible_tracks(
        self,
        source_id: str | None,
        *,
        extractor_version: str,
        normalization_version: str,
        force: bool,
    ) -> list[Track]:
        """Return present tracks requiring extraction based on persisted input facts."""
        where_source = "" if source_id is None else "AND t.source_id = ?"
        parameters: tuple[Any, ...] = (
            extractor_version,
            normalization_version,
            *((source_id,) if source_id is not None else ()),
        )
        if force:
            query = f"""
                SELECT t.id, t.source_id, t.relative_path, t.filename, t.extension, t.size_bytes,
                       t.mtime_ns, t.presence_status
                FROM tracks t WHERE t.presence_status = 'present' {where_source} ORDER BY t.id
            """
            rows = self._database.execute(query, parameters[2:]).fetchall()
            return [_track_from_row(row) for row in rows]
        query = f"""
            SELECT t.id, t.source_id, t.relative_path, t.filename, t.extension, t.size_bytes,
                   t.mtime_ns, t.presence_status
            FROM tracks t LEFT JOIN embedded_metadata m ON m.track_id = t.id
            WHERE t.presence_status = 'present' {where_source} AND (
                m.track_id IS NULL OR m.input_size_bytes IS NULL OR m.input_mtime_ns IS NULL OR
                m.input_size_bytes != t.size_bytes OR m.input_mtime_ns != t.mtime_ns OR
                m.extractor_version != ? OR m.normalization_version != ?
            ) ORDER BY t.id
        """
        if source_id is None:
            parameters = (extractor_version, normalization_version)
        else:
            parameters = (source_id, extractor_version, normalization_version)
        rows = self._database.execute(query, parameters).fetchall()
        return [_track_from_row(row) for row in rows]

    def present_count(self, source_id: str | None) -> int:
        """Count present tracks in the requested source scope."""
        if source_id is None:
            query = "SELECT COUNT(*) FROM tracks WHERE presence_status = 'present'"
            return int(self._database.scalar(query))
        return int(
            self._database.scalar(
                "SELECT COUNT(*) FROM tracks WHERE source_id = ? AND presence_status = 'present'",
                (source_id,),
            )
        )

    def current(self, track_id: int) -> tuple[Any, ...] | None:
        row = self._database.execute(
            "SELECT title, artist, album_artist, album, track_number, disc_number, genre, "
            "date, year, composer, comment, tag_bpm, tag_initial_key, grouping "
            "FROM embedded_metadata WHERE track_id = ?",
            (track_id,),
        ).fetchone()
        return cast(tuple[Any, ...] | None, row)

    def upsert(
        self,
        track: Track,
        values: tuple[Any, ...],
        *,
        extracted_at: str,
        extractor_version: str,
        normalization_version: str,
    ) -> None:
        self._database.execute(
            """
            INSERT INTO embedded_metadata (
                track_id, title, artist, album_artist, album, track_number, disc_number, genre,
                date, year, composer, comment, tag_bpm, tag_initial_key, grouping,
                metadata_extracted_at, extractor_version, input_size_bytes, input_mtime_ns,
                normalization_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_id) DO UPDATE SET
                title=excluded.title, artist=excluded.artist, album_artist=excluded.album_artist,
                album=excluded.album, track_number=excluded.track_number,
                disc_number=excluded.disc_number, genre=excluded.genre, date=excluded.date,
                year=excluded.year, composer=excluded.composer, comment=excluded.comment,
                tag_bpm=excluded.tag_bpm, tag_initial_key=excluded.tag_initial_key,
                grouping=excluded.grouping, metadata_extracted_at=excluded.metadata_extracted_at,
                extractor_version=excluded.extractor_version,
                input_size_bytes=excluded.input_size_bytes, input_mtime_ns=excluded.input_mtime_ns,
                normalization_version=excluded.normalization_version
            """,
            (
                track.id,
                *values,
                extracted_at,
                extractor_version,
                track.size_bytes,
                track.mtime_ns,
                normalization_version,
            ),
        )


@dataclass(frozen=True)
class TrackObservation:
    """Lifecycle consequences of observing one track."""

    track_id: int
    discovered: bool
    restored: bool
    metadata_changed: bool


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
