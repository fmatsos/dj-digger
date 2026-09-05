"""Catalog persistence for audio fingerprints and duplicate groups."""

from dataclasses import dataclass
from datetime import UTC, datetime

from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.duplicates.fingerprint import FINGERPRINT_VERSION, Fingerprint


@dataclass(frozen=True)
class DuplicateGroupMember:
    """One present track belonging to a duplicate group."""

    track: Track
    source_id: str


@dataclass(frozen=True)
class DuplicateGroup:
    """Two or more present tracks that share a complete fingerprint hash."""

    fingerprint_hash: str
    members: tuple[DuplicateGroupMember, ...]


class DuplicateRepository:
    """Reads and writes fingerprints, and derives duplicate groups from them."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def present_tracks(self, source_id: str | None) -> list[Track]:
        """List present tracks from enabled sources, optionally scoped to one source."""
        query = """
            SELECT t.id, t.source_id, t.relative_path, t.filename, t.extension, t.size_bytes,
                   t.mtime_ns, t.presence_status
            FROM tracks t JOIN library_sources s ON s.source_id = t.source_id
            WHERE t.presence_status = 'present' AND s.enabled = 1
        """
        parameters: list[object] = []
        if source_id is not None:
            query += " AND t.source_id = ?"
            parameters.append(source_id)
        query += " ORDER BY t.source_id, t.relative_path, t.id"
        return [Track(*row) for row in self._database.execute(query, parameters).fetchall()]

    def reusable_fingerprint(self, track: Track, fingerprint_version: str) -> Fingerprint | None:
        """Return the current fingerprint if it still matches this track's input identity."""
        row = self._database.execute(
            """
            SELECT fingerprint, fingerprint_hash, fingerprint_version
            FROM audio_fingerprints
            WHERE track_id = ? AND input_size_bytes = ? AND input_mtime_ns = ?
              AND fingerprint_version = ?
            """,
            (track.id, track.size_bytes, track.mtime_ns, fingerprint_version),
        ).fetchone()
        return None if row is None else Fingerprint(*row)

    def upsert_fingerprint(self, track: Track, fingerprint: Fingerprint) -> None:
        """Persist a successful fingerprint result immediately."""
        self._database.execute(
            """
            INSERT INTO audio_fingerprints (
                track_id, fingerprint, fingerprint_hash, fingerprint_version,
                input_size_bytes, input_mtime_ns, fingerprinted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_id) DO UPDATE SET
                fingerprint=excluded.fingerprint, fingerprint_hash=excluded.fingerprint_hash,
                fingerprint_version=excluded.fingerprint_version,
                input_size_bytes=excluded.input_size_bytes,
                input_mtime_ns=excluded.input_mtime_ns, fingerprinted_at=excluded.fingerprinted_at
            """,
            (
                track.id,
                fingerprint.fingerprint,
                fingerprint.fingerprint_hash,
                fingerprint.fingerprint_version,
                track.size_bytes,
                track.mtime_ns,
                _now(),
            ),
        )

    def groups(self, source_id: str | None) -> list[DuplicateGroup]:
        """Return duplicate groups of at least two present tracks, in deterministic order."""
        query = """
            SELECT af.fingerprint_hash, t.id, t.source_id, t.relative_path, t.filename,
                   t.extension, t.size_bytes, t.mtime_ns, t.presence_status
            FROM audio_fingerprints af
            JOIN tracks t ON t.id = af.track_id
            JOIN library_sources s ON s.source_id = t.source_id
            WHERE t.presence_status = 'present' AND s.enabled = 1
              AND af.fingerprint_version = ?
              AND af.input_size_bytes = t.size_bytes
              AND af.input_mtime_ns = t.mtime_ns
        """
        parameters: list[object] = [FINGERPRINT_VERSION]
        if source_id is not None:
            query += " AND t.source_id = ?"
            parameters.append(source_id)
        query += """
            AND af.fingerprint_hash IN (
                SELECT af2.fingerprint_hash
                FROM audio_fingerprints af2
                JOIN tracks t2 ON t2.id = af2.track_id
                JOIN library_sources s2 ON s2.source_id = t2.source_id
                WHERE t2.presence_status = 'present' AND s2.enabled = 1
                  AND af2.fingerprint_version = ?
                  AND af2.input_size_bytes = t2.size_bytes AND af2.input_mtime_ns = t2.mtime_ns
        """
        parameters.append(FINGERPRINT_VERSION)
        if source_id is not None:
            query += " AND t2.source_id = ?"
            parameters.append(source_id)
        query += """
                GROUP BY af2.fingerprint_hash
                HAVING COUNT(*) >= 2
            )
            ORDER BY af.fingerprint_hash, t.source_id, t.relative_path, t.id
        """
        rows = self._database.execute(query, parameters).fetchall()
        groups: dict[str, list[DuplicateGroupMember]] = {}
        for row in rows:
            fingerprint_hash = row[0]
            track = Track(*row[1:])
            groups.setdefault(fingerprint_hash, []).append(
                DuplicateGroupMember(track=track, source_id=track.source_id)
            )
        return [
            DuplicateGroup(fingerprint_hash=fingerprint_hash, members=tuple(members))
            for fingerprint_hash, members in groups.items()
        ]

    def invalidate_stale_quality_selections(self) -> None:
        """Drop selections whose preferred track no longer matches a current fingerprint."""
        self._database.execute(
            """
            DELETE FROM duplicate_quality_selections
            WHERE (source_id, fingerprint_hash) IN (
                SELECT dqs.source_id, dqs.fingerprint_hash
                FROM duplicate_quality_selections dqs
                LEFT JOIN tracks t
                    ON t.id = dqs.preferred_track_id AND t.presence_status = 'present'
                LEFT JOIN audio_fingerprints af
                    ON af.track_id = dqs.preferred_track_id
                   AND af.fingerprint_hash = dqs.fingerprint_hash
                   AND af.fingerprint_version = ?
                   AND af.input_size_bytes = t.size_bytes
                   AND af.input_mtime_ns = t.mtime_ns
                LEFT JOIN technical_audio_metadata tam
                    ON tam.track_id = dqs.preferred_track_id
                   AND t.id IS NOT NULL
                   AND tam.input_size_bytes = t.size_bytes
                   AND tam.input_mtime_ns = t.mtime_ns
                WHERE t.id IS NULL OR af.track_id IS NULL OR tam.track_id IS NULL
            )
            """,
            (FINGERPRINT_VERSION,),
        )

    def replace_quality_selections(
        self, source_id: str, selections: dict[str, int], ranking_version: str
    ) -> None:
        """Atomically replace every quality selection for one source."""
        now = _now()
        self._database.execute(
            "DELETE FROM duplicate_quality_selections WHERE source_id = ?", (source_id,)
        )
        for fingerprint_hash, preferred_track_id in selections.items():
            self._database.execute(
                """
                INSERT INTO duplicate_quality_selections (
                    source_id, fingerprint_hash, preferred_track_id, ranking_version, selected_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (source_id, fingerprint_hash, preferred_track_id, ranking_version, now),
            )

    def quality_selections(self, source_id: str | None) -> dict[tuple[str, str], int]:
        """Return preferred_track_id keyed by (source_id, fingerprint_hash)."""
        query = (
            "SELECT source_id, fingerprint_hash, preferred_track_id FROM "
            "duplicate_quality_selections"
        )
        parameters: list[object] = []
        if source_id is not None:
            query += " WHERE source_id = ?"
            parameters.append(source_id)
        return {(row[0], row[1]): row[2] for row in self._database.execute(query, parameters)}


def _now() -> str:
    return datetime.now(UTC).isoformat()
