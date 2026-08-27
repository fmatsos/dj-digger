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
            SELECT track_id, source_id, relative_path, filename, extension,
                   size_bytes, mtime_ns, set_eligible,
                   title, artist, album_artist, album, track_number,
                   disc_number, genre, date, year, composer, comment,
                   tag_bpm, tag_initial_key, grouping,
                   duration_seconds, sample_rate, channels, codec,
                   container, bitrate, lossless
            FROM library_tracks
            ORDER BY source_id, relative_path, track_id
            """
        ).fetchall()
