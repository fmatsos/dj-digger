"""Append-only persistence for versioned audio analysis results."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from dj_digger.analysis.aggregation import canonical_json
from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track


def _now() -> str:
    return datetime.now(UTC).isoformat()


class AnalysisPersistence:
    """Store independent analysis attempts without replacing prior results."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def store_success(
        self,
        track: Track,
        identity: AnalysisIdentity,
        payload: Mapping[str, Any],
        *,
        confidence: float | None = None,
    ) -> int:
        """Append a successful result and return its immutable analysis identity."""
        now = _now()
        with self._database.transaction():
            run_id = self._start_run(identity, now)
            cursor = self._database.execute(
                """
                INSERT INTO audio_analysis (
                    track_id, analysis_run_id, analysis_schema_version, analyzer_version,
                    config_hash, input_size_bytes, input_mtime_ns, analysis_status,
                    analysis_confidence, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'succeeded', ?, ?, ?)
                """,
                (
                    track.id,
                    run_id,
                    identity.schema_version,
                    identity.analyzer_version,
                    identity.config_hash,
                    track.size_bytes,
                    track.mtime_ns,
                    confidence,
                    canonical_json(payload),
                    now,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an analysis id")
            analysis_id = int(cursor.lastrowid)
            self._finish_run(run_id, now)
            self._append_event(
                track.id, run_id, "analysis_completed", {"analysis_id": analysis_id}, now
            )
        return analysis_id

    def store_failure(self, track: Track, identity: AnalysisIdentity, error: str) -> None:
        """Append a failed attempt while retaining every preceding successful result."""
        now = _now()
        with self._database.transaction():
            run_id = self._start_run(identity, now)
            self._database.execute(
                """
                INSERT OR IGNORE INTO audio_analysis (
                    track_id, analysis_run_id, analysis_schema_version, analyzer_version,
                    config_hash, input_size_bytes, input_mtime_ns, analysis_status,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'failed', ?, ?)
                """,
                (
                    track.id,
                    run_id,
                    identity.schema_version,
                    identity.analyzer_version,
                    identity.config_hash,
                    track.size_bytes,
                    track.mtime_ns,
                    canonical_json({"error": error}),
                    now,
                ),
            )
            self._database.execute(
                "UPDATE analysis_runs SET status = 'failed', finished_at = ? WHERE id = ?",
                (now, run_id),
            )
            self._append_event(track.id, run_id, "analysis_failed", {"error": error}, now)

    def _start_run(self, identity: AnalysisIdentity, now: str) -> int:
        cursor = self._database.execute(
            """
            INSERT INTO analysis_runs (
                started_at, status, analysis_schema_version, analyzer_version, config_hash
            ) VALUES (?, 'running', ?, ?, ?)
            """,
            (now, identity.schema_version, identity.analyzer_version, identity.config_hash),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an analysis run id")
        return int(cursor.lastrowid)

    def _finish_run(self, run_id: int, now: str) -> None:
        self._database.execute(
            "UPDATE analysis_runs SET status = 'succeeded', finished_at = ? WHERE id = ?",
            (now, run_id),
        )

    def _append_event(
        self, track_id: int, run_id: int, event_type: str, payload: Mapping[str, Any], now: str
    ) -> None:
        self._database.execute(
            """
            INSERT INTO track_events (
                track_id, occurred_at, analysis_run_id, event_type, payload_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (track_id, now, run_id, event_type, canonical_json(payload)),
        )
