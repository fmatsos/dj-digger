"""Read-only catalog projections backed by stable SQLite views."""

from typing import Any

from dj_digger.catalog.database import Database


class LibraryReadRepository:
    """Read the public library projection without exposing write operations."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def list_tracks(
        self, *, limit: int, after_track_id: int | None = None
    ) -> list[tuple[Any, ...]]:
        """List present tracks in track-id order using keyset pagination."""
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        if after_track_id is None:
            return self._database.execute(
                "SELECT * FROM library_tracks ORDER BY track_id LIMIT ?", (limit,)
            ).fetchall()
        return self._database.execute(
            "SELECT * FROM library_tracks WHERE track_id > ? ORDER BY track_id LIMIT ?",
            (after_track_id, limit),
        ).fetchall()

    def export_rows(self) -> list[tuple[Any, ...]]:
        """Return the public track export projection in its stable publication order."""
        return self._database.execute(
            """
            SELECT lt.track_id, lt.source_id, lt.relative_path, lt.filename, lt.extension,
                   lt.size_bytes, lt.mtime_ns, lt.set_eligible,
                   lt.title, lt.artist, lt.album_artist, lt.album, lt.track_number,
                   lt.disc_number, lt.genre, lt.date, lt.year, lt.composer, lt.comment,
                   lt.tag_bpm, lt.tag_initial_key, lt.grouping,
                   lt.duration_seconds, lt.sample_rate, lt.channels, lt.codec,
                   lt.container, lt.bitrate, lt.lossless,
                   dup.fingerprint_hash AS duplicate_group_id,
                   CASE
                       WHEN dup.fingerprint_hash IS NULL THEN NULL
                       WHEN dqs.preferred_track_id IS NULL THEN NULL
                       WHEN dqs.preferred_track_id = lt.track_id THEN 1
                       ELSE 0
                   END AS duplicate_best_quality
                   ,lt.integrated_lufs, lt.loudness_range_lu, lt.true_peak_dbtp,
                   lt.short_term_lufs_p50, lt.short_term_lufs_p95,
                   lt.peak_to_loudness_ratio_db, lt.required_gain_db,
                   lt.available_gain_db, lt.gain_deficit_db
            FROM library_tracks lt
            LEFT JOIN (
                SELECT af.track_id, af.fingerprint_hash
                FROM audio_fingerprints af
                JOIN tracks t ON t.id = af.track_id
                JOIN library_sources s ON s.source_id = t.source_id
                WHERE t.presence_status = 'present' AND s.enabled = 1
                  AND af.fingerprint_hash IN (
                      SELECT af2.fingerprint_hash
                      FROM audio_fingerprints af2
                      JOIN tracks t2 ON t2.id = af2.track_id
                      JOIN library_sources s2 ON s2.source_id = t2.source_id
                      WHERE t2.presence_status = 'present' AND s2.enabled = 1
                      GROUP BY af2.fingerprint_hash
                      HAVING COUNT(*) >= 2
                  )
            ) dup ON dup.track_id = lt.track_id
            LEFT JOIN duplicate_quality_selections dqs
                ON dqs.source_id = lt.source_id AND dqs.fingerprint_hash = dup.fingerprint_hash
            ORDER BY lt.source_id, lt.relative_path, lt.track_id
            """
        ).fetchall()
