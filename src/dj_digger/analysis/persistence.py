"""Append-only persistence for versioned audio analysis results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dj_digger.analysis.aggregation import canonical_json
from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.analysis.extractor import AnalysisExtractionResult, Stage
from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class AnalysisOutcome:
    """Typed result of one extraction, including a normalized failure stage."""

    track: Track
    extraction: Extraction
    error: str | None
    stage: Stage


type Extraction = AnalysisExtractionResult | Mapping[str, object]
type LegacyOutcome = tuple[Track, Extraction, str | None, Stage]
type Outcome = AnalysisOutcome | LegacyOutcome


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

    def persist_run(
        self,
        identity: AnalysisIdentity,
        outcomes: Sequence[Outcome],
        *,
        eligible: int,
        reused: int,
        started_at: str,
        finished_at: str,
    ) -> tuple[int, int, int]:
        """Persist one aggregate run, attempts, sections and events atomically.

        ``outcomes`` contains ``(track, extraction, error, stage)``.  Extraction may
        be an ``AnalysisExtractionResult`` or a plain mapping for compatibility.
        """
        normalized = [_normalize_outcome(outcome) for outcome in outcomes]
        analyzed = sum(outcome.error is None for outcome in normalized)
        failed = len(outcomes) - analyzed
        status = "succeeded" if failed == 0 else ("failed" if analyzed == 0 else "partial")
        with self._database.transaction():
            cursor = self._database.execute(
                """INSERT INTO analysis_runs
                (started_at, finished_at, status, eligible, analyzed, reused, failed,
                 analysis_schema_version, analyzer_version, config_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (started_at, finished_at, status, eligible, analyzed, reused, failed,
                 identity.schema_version, identity.analyzer_version, identity.config_hash),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an analysis run id")
            run_id = int(cursor.lastrowid)
            for outcome in normalized:
                track, extraction, error, stage = (
                    outcome.track, outcome.extraction, outcome.error, outcome.stage
                )
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
                        track, identity, run_id, "succeeded", payload, finished_at, confidence
                    )
                    if sections is not None:
                        self._insert_sections(analysis_id, sections)
                    self._append_event(
                        track.id,
                        run_id,
                        "analysis_completed",
                        {"analysis_id": analysis_id},
                        finished_at,
                    )
                else:
                    self._insert_attempt(
                        track, identity, run_id, "failed", {"error": error, "stage": stage},
                        finished_at, None
                    )
                    self._append_event(
                        track.id,
                        run_id,
                        "analysis_failed",
                        {"error": error, "stage": stage},
                        finished_at,
                    )
        return run_id, analyzed, failed

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

    def store_failure(self, track: Track, identity: AnalysisIdentity, error: str) -> None:
        """Append a failed attempt while retaining every preceding successful result."""
        now = _now()
        with self._database.transaction():
            run_id = self._start_run(identity, now)
            self._database.execute(
                """
                INSERT INTO audio_analysis (
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


def _normalize_outcome(outcome: Outcome) -> AnalysisOutcome:
    if isinstance(outcome, AnalysisOutcome):
        return outcome
    track, extraction, error, stage = outcome
    return AnalysisOutcome(track, extraction, error, stage)
