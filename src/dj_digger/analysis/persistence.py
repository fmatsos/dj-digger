"""Append-only persistence for versioned audio analysis results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dj_digger.analysis.aggregation import canonical_json
from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.analysis.extractor import AnalysisExtractionResult, Stage
from dj_digger.catalog.current_analysis import CurrentAnalysisProjector
from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track


@dataclass(frozen=True)
class AnalysisOutcome:
    """Typed result of one extraction, including a normalized failure stage."""

    track: Track
    extraction: Extraction
    error: str | None
    stage: Stage


type Extraction = AnalysisExtractionResult | Mapping[str, object]


class AnalysisPersistence:
    """Store independent analysis attempts without replacing prior results."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def start_run(
        self,
        identity: AnalysisIdentity,
        *,
        eligible: int,
        reused: int,
        started_at: str,
    ) -> int:
        """Create a committed aggregate run before any extraction starts."""
        with self._database.transaction():
            cursor = self._database.execute(
                """INSERT INTO analysis_runs
                (started_at, status, eligible, analyzed, reused, failed,
                 analysis_schema_version, analyzer_version, config_hash)
                VALUES (?, 'running', ?, 0, ?, 0, ?, ?, ?)""",
                (
                    started_at,
                    eligible,
                    reused,
                    identity.schema_version,
                    identity.analyzer_version,
                    identity.config_hash,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an analysis run id")
            return int(cursor.lastrowid)

    def persist_outcome(
        self,
        run_id: int,
        identity: AnalysisIdentity,
        outcome: AnalysisOutcome,
        *,
        occurred_at: str,
    ) -> tuple[int, int]:
        """Commit one attempt, its details, event and aggregate counter atomically."""
        track, extraction, error, stage = (
            outcome.track,
            outcome.extraction,
            outcome.error,
            outcome.stage,
        )
        with self._database.transaction():
            if error is None:
                if isinstance(extraction, AnalysisExtractionResult):
                    payload = extraction.payload
                    confidence = extraction.confidence
                    sections = extraction.sections
                else:
                    payload = extraction
                    confidence = None
                    sections = None
                analysis_id = self._insert_attempt(
                    track,
                    identity,
                    run_id,
                    "succeeded",
                    payload,
                    occurred_at,
                    confidence,
                )
                if sections is not None:
                    self._insert_sections(analysis_id, sections)
                CurrentAnalysisProjector(self._database).advance(analysis_id)
                self._append_event(
                    track.id,
                    run_id,
                    "analysis_completed",
                    {"analysis_id": analysis_id},
                    occurred_at,
                )
                self._database.execute(
                    "UPDATE analysis_runs SET analyzed = analyzed + 1 WHERE id = ?",
                    (run_id,),
                )
            else:
                self._insert_attempt(
                    track,
                    identity,
                    run_id,
                    "failed",
                    {"error": error, "stage": stage},
                    occurred_at,
                    None,
                )
                self._append_event(
                    track.id,
                    run_id,
                    "analysis_failed",
                    {"error": error, "stage": stage},
                    occurred_at,
                )
                self._database.execute(
                    "UPDATE analysis_runs SET failed = failed + 1 WHERE id = ?",
                    (run_id,),
                )
            row = self._database.execute(
                "SELECT analyzed, failed FROM analysis_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"analysis run {run_id} does not exist")
            return int(row[0]), int(row[1])

    def finish_run(self, run_id: int, *, finished_at: str) -> tuple[str, int, int]:
        """Finalize a run from its committed aggregate counters."""
        with self._database.transaction():
            row = self._database.execute(
                "SELECT eligible, analyzed, reused, failed FROM analysis_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"analysis run {run_id} does not exist")
            eligible, analyzed, reused, failed = (int(value) for value in row)
            status = _derive_status(eligible, analyzed, reused, failed)
            self._database.execute(
                "UPDATE analysis_runs SET status = ?, finished_at = ? WHERE id = ?",
                (status, finished_at, run_id),
            )
        return status, analyzed, failed

    def reconcile_running_runs(self, *, finished_at: str) -> int:
        """Finalize abandoned runs from their already committed attempts."""
        with self._database.transaction():
            runs = self._database.execute(
                "SELECT id, eligible, reused FROM analysis_runs WHERE status = 'running'"
            ).fetchall()
            for run_id, eligible, reused in runs:
                analyzed, failed = self._database.execute(
                    """SELECT
                        COALESCE(SUM(analysis_status = 'succeeded'), 0),
                        COALESCE(SUM(analysis_status = 'failed'), 0)
                    FROM audio_analysis WHERE analysis_run_id = ?""",
                    (run_id,),
                ).fetchone()
                analyzed = int(analyzed)
                failed = int(failed)
                status = _derive_status(int(eligible), analyzed, int(reused), failed)
                self._database.execute(
                    """UPDATE analysis_runs
                    SET status = ?, analyzed = ?, failed = ?, finished_at = ?
                    WHERE id = ?""",
                    (status, analyzed, failed, finished_at, run_id),
                )
        return len(runs)

    def _insert_attempt(
        self, track: Track, identity: AnalysisIdentity, run_id: int, status: str,
        payload: Mapping[str, Any], now: str, confidence: float | None,
    ) -> int:
        cursor = self._database.execute(
            """INSERT INTO audio_analysis
            (track_id, analysis_run_id, analysis_schema_version, analyzer_version, config_hash,
             input_size_bytes, input_mtime_ns, analysis_status, analysis_confidence,
             payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                track.id, run_id, identity.schema_version, identity.analyzer_version,
                identity.config_hash, track.size_bytes, track.mtime_ns, status, confidence,
                canonical_json(payload), now,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an analysis id")
        return int(cursor.lastrowid)

    def _insert_sections(self, analysis_id: int, sections: Any) -> None:
        # Store one row per section; the extractor's document wrapper is accepted too.
        if isinstance(sections, Mapping):
            rows = sections.get("sections", [])
        elif isinstance(sections, (list, tuple)):
            rows = sections
        else:
            raise ValueError("analysis sections must be a document or sequence")
        if not isinstance(rows, (list, tuple)):
            raise ValueError("analysis sections must contain a sequence")
        for index, section in enumerate(rows):
            if not isinstance(section, Mapping):
                raise ValueError("analysis section must be an object")
            self._database.execute(
                "INSERT INTO track_sections "
                "(audio_analysis_id, section_index, payload_json) VALUES (?, ?, ?)",
                (analysis_id, index, canonical_json(section)),
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

def _derive_status(eligible: int, analyzed: int, reused: int, failed: int) -> str:
    completed = analyzed + reused
    accounted = completed + failed
    if failed == 0 and accounted >= eligible:
        return "succeeded"
    if completed > 0:
        return "partial"
    return "failed"
