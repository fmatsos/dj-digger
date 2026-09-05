"""Append-only mastering attempts and rebuildable current projections."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.duplicates.mastering import (
    MASTERING_ANALYSIS_VERSION,
    DjMetrics,
    MasteringMeasurements,
    derive_dj_metrics,
)


@dataclass(frozen=True)
class CurrentMasteringAnalysis:
    analysis_id: int
    track_id: int
    analysis_version: str
    measurements: MasteringMeasurements


@dataclass(frozen=True)
class CurrentDjAnalysis:
    track_id: int
    mastering_analysis_id: int
    target_lufs: float
    target_peak_dbtp: float
    metrics: DjMetrics


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MasteringRepository:
    """Own all catalog writes for mastering analysis."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def reusable(self, track: Track, analysis_version: str) -> CurrentMasteringAnalysis | None:
        row = self._database.execute(
            """SELECT c.mastering_analysis_id, c.track_id, c.analysis_version,
                      c.integrated_lufs, c.loudness_range_lu, c.true_peak_dbtp,
                      c.short_term_lufs_p50, c.short_term_lufs_p95,
                      c.peak_to_loudness_ratio_db
               FROM current_mastering_analysis c
               JOIN mastering_analysis a ON a.id = c.mastering_analysis_id
               WHERE c.track_id = ? AND c.analysis_version = ?
                 AND a.input_size_bytes = ? AND a.input_mtime_ns = ?""",
            (track.id, analysis_version, track.size_bytes, track.mtime_ns),
        ).fetchone()
        return None if row is None else self._current_from_row(row)

    def persist_success(
        self, track: Track, analysis_version: str, measurements: MasteringMeasurements
    ) -> int:
        return self._persist(track, analysis_version, "succeeded", None, None, measurements)

    def persist_failure(self, track: Track, analysis_version: str, stage: str, message: str) -> int:
        return self._persist(track, analysis_version, "failed", stage, message[:8192], None)

    def _persist(
        self,
        track: Track,
        version: str,
        status: str,
        stage: str | None,
        message: str | None,
        measurements: MasteringMeasurements | None,
    ) -> int:
        values: tuple[Any, ...] = (
            track.id,
            version,
            track.size_bytes,
            track.mtime_ns,
            status,
            stage,
            message,
            _now(),
        )
        metrics: tuple[float | None, ...] = (
            (None,) * 6
            if measurements is None
            else (
                measurements.integrated_lufs,
                measurements.loudness_range_lu,
                measurements.true_peak_dbtp,
                measurements.short_term_lufs_p50,
                measurements.short_term_lufs_p95,
                measurements.peak_to_loudness_ratio_db,
            )
        )
        with self._database.transaction():
            cursor = self._database.execute(
                """INSERT INTO mastering_analysis
                   (track_id, analysis_version, input_size_bytes, input_mtime_ns, status,
                    error_stage, error_message, analyzed_at, integrated_lufs,
                    loudness_range_lu, true_peak_dbtp, short_term_lufs_p50,
                    short_term_lufs_p95, peak_to_loudness_ratio_db)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values + metrics,
            )
            if cursor.lastrowid is None:
                raise RuntimeError("mastering analysis insert returned no row id")
            analysis_id = cursor.lastrowid
            if status == "succeeded":
                self._database.execute(
                    """INSERT INTO current_mastering_analysis
                       (track_id, mastering_analysis_id, analysis_version,
                        integrated_lufs, loudness_range_lu, true_peak_dbtp,
                        short_term_lufs_p50, short_term_lufs_p95,
                        peak_to_loudness_ratio_db, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(track_id) DO UPDATE SET
                         mastering_analysis_id=excluded.mastering_analysis_id,
                         analysis_version=excluded.analysis_version,
                         integrated_lufs=excluded.integrated_lufs,
                         loudness_range_lu=excluded.loudness_range_lu,
                         true_peak_dbtp=excluded.true_peak_dbtp,
                         short_term_lufs_p50=excluded.short_term_lufs_p50,
                         short_term_lufs_p95=excluded.short_term_lufs_p95,
                         peak_to_loudness_ratio_db=excluded.peak_to_loudness_ratio_db,
                         updated_at=excluded.updated_at""",
                    (track.id, analysis_id, version, *metrics, _now()),
                )
        return analysis_id

    def current_for_tracks(
        self, track_ids: list[int], expected_version: str = MASTERING_ANALYSIS_VERSION
    ) -> dict[int, CurrentMasteringAnalysis]:
        if not track_ids:
            return {}
        placeholders = ",".join("?" for _ in track_ids)
        rows = self._database.execute(
            f"""SELECT c.mastering_analysis_id, c.track_id, c.analysis_version,
                c.integrated_lufs, c.loudness_range_lu, c.true_peak_dbtp,
                c.short_term_lufs_p50, c.short_term_lufs_p95, c.peak_to_loudness_ratio_db
                FROM current_mastering_analysis c
                JOIN mastering_analysis a ON a.id = c.mastering_analysis_id
                JOIN tracks t ON t.id = c.track_id
                WHERE c.track_id IN ({placeholders})
                  AND a.input_size_bytes = t.size_bytes
                  AND a.input_mtime_ns = t.mtime_ns
                  AND a.analysis_version = c.analysis_version"""
            + (" AND c.analysis_version = ?" if expected_version is not None else ""),
            [*track_ids, *([expected_version] if expected_version is not None else [])],
        ).fetchall()
        return {int(row[1]): self._current_from_row(row) for row in rows}

    def rebuild_current(self, expected_version: str) -> int:
        with self._database.transaction():
            self._database.execute("DELETE FROM current_mastering_analysis")
            self._database.execute(
                """INSERT INTO current_mastering_analysis
                (track_id, mastering_analysis_id, analysis_version, integrated_lufs,
                 loudness_range_lu, true_peak_dbtp, short_term_lufs_p50, short_term_lufs_p95,
                 peak_to_loudness_ratio_db, updated_at)
                SELECT a.track_id, a.id, a.analysis_version, a.integrated_lufs,
                 a.loudness_range_lu, a.true_peak_dbtp, a.short_term_lufs_p50,
                 a.short_term_lufs_p95, a.peak_to_loudness_ratio_db, a.analyzed_at
                FROM mastering_analysis a JOIN (
                  SELECT a2.track_id, MAX(a2.id) AS id FROM mastering_analysis a2
                  JOIN tracks t ON t.id = a2.track_id
                  WHERE a2.status='succeeded' AND a2.analysis_version = ?
                    AND a2.input_size_bytes=t.size_bytes
                    AND a2.input_mtime_ns=t.mtime_ns GROUP BY track_id
                ) latest ON latest.id = a.id""",
                (expected_version,),
            )
        return int(self._database.scalar("SELECT COUNT(*) FROM current_mastering_analysis"))

    def rebuild_dj(self, target_lufs: float, target_peak_dbtp: float) -> int:
        with self._database.transaction():
            rows = self._database.execute(
                "SELECT track_id, mastering_analysis_id, integrated_lufs, true_peak_dbtp "
                "FROM current_mastering_analysis WHERE analysis_version = ?",
                (MASTERING_ANALYSIS_VERSION,),
            ).fetchall()
            self._database.execute("DELETE FROM current_dj_analysis")
            for track_id, analysis_id, integrated, peak in rows:
                metrics = derive_dj_metrics(
                    integrated, peak, target_lufs=target_lufs, target_peak_dbtp=target_peak_dbtp
                )
                self._database.execute(
                    """INSERT INTO current_dj_analysis
                    (track_id, mastering_analysis_id, dj_target_lufs, dj_target_true_peak_dbtp,
                     required_gain_db, available_gain_db, gain_deficit_db)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        track_id,
                        analysis_id,
                        target_lufs,
                        target_peak_dbtp,
                        metrics.required_gain_db,
                        metrics.available_gain_db,
                        metrics.gain_deficit_db,
                    ),
                )
        return len(rows)

    @staticmethod
    def _current_from_row(row: tuple[Any, ...]) -> CurrentMasteringAnalysis:
        return CurrentMasteringAnalysis(
            int(row[0]),
            int(row[1]),
            str(row[2]),
            MasteringMeasurements(*(None if value is None else float(value) for value in row[3:9])),
        )
