"""Bounded, deterministic orchestration for immutable audio analysis attempts."""

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dj_digger.analysis.aggregation import canonical_json
from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.analysis.eligibility import AnalysisEligibility
from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import TrackRepository

AnalysisExtractor = Callable[[Track], Mapping[str, Any]]


@dataclass(frozen=True)
class AnalysisRunResult:
    """Counters for one aggregate analysis run."""

    run_id: int
    eligible: int
    analyzed: int
    reused: int
    failed: int


class AnalysisPipeline:
    """Compute independent tracks concurrently and persist them serially."""

    def __init__(
        self, database: Database, identity: AnalysisIdentity, extract: AnalysisExtractor
    ) -> None:
        self._database = database
        self._identity = identity
        self._extract = extract
        self._tracks = TrackRepository(database)

    def run(
        self,
        *,
        source_id: str | None = None,
        path_prefix: str | None = None,
        limit: int | None = None,
        force: bool = False,
        workers: int = 1,
    ) -> AnalysisRunResult:
        """Analyze selected tracks, preserving reuse and append-only history."""
        if path_prefix is not None and not path_prefix.strip():
            raise ValueError("path prefix must not be blank")
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        if workers < 1:
            raise ValueError("workers must be positive")

        selected = self._all_eligible(source_id, path_prefix) if force else AnalysisEligibility(
            self._tracks
        ).pending(self._identity, source_id, path_prefix)
        if limit is not None:
            selected = selected[:limit]
        started = _now()

        reusable = [track for track in selected if self._is_reusable(track)]
        pending = [track for track in selected if track not in reusable]
        outcomes = self._extract_all(pending, workers)
        finished = _now()
        analyzed = sum(error is None for _, _, error in outcomes)
        failed = len(outcomes) - analyzed

        with self._database.transaction():
            run_id = self._start_run(
                started, finished, len(selected), analyzed, len(reusable), failed
            )
            for track, payload, error in outcomes:
                if error is None:
                    self._store_success(track, run_id, payload, finished)
                else:
                    self._store_failure(track, run_id, error, finished)
        return AnalysisRunResult(run_id, len(selected), analyzed, len(reusable), failed)

    def _all_eligible(self, source_id: str | None, path_prefix: str | None) -> list[Track]:
        query = """
            SELECT t.id, t.source_id, t.relative_path, t.filename, t.extension, t.size_bytes,
                   t.mtime_ns, t.presence_status
            FROM tracks t JOIN library_sources s ON s.source_id = t.source_id
            WHERE t.presence_status = 'present' AND s.enabled = 1 AND s.analyze = 1
        """
        parameters: list[object] = []
        if source_id is not None:
            query += " AND t.source_id = ?"
            parameters.append(source_id)
        if path_prefix is not None:
            escaped = path_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query += " AND t.relative_path LIKE ? ESCAPE '\\'"
            parameters.append(f"{escaped}%")
        query += " ORDER BY t.source_id, t.relative_path, t.id"
        return [Track(*row) for row in self._database.execute(query, parameters).fetchall()]

    def _is_reusable(self, track: Track) -> bool:
        return self._database.scalar(
            """
            SELECT 1 FROM audio_analysis
            WHERE track_id = ? AND input_size_bytes = ? AND input_mtime_ns = ?
              AND analysis_schema_version = ? AND analyzer_version = ? AND config_hash = ?
              AND analysis_status = 'succeeded'
            LIMIT 1
            """,
            (
                track.id,
                track.size_bytes,
                track.mtime_ns,
                self._identity.schema_version,
                self._identity.analyzer_version,
                self._identity.config_hash,
            ),
        ) is not None

    def _extract_all(
        self, tracks: list[Track], workers: int
    ) -> list[tuple[Track, Mapping[str, Any], str | None]]:
        def extract(track: Track) -> tuple[Track, Mapping[str, Any], str | None]:
            try:
                return track, self._extract(track), None
            except Exception as error:
                return track, {}, str(error)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(extract, tracks))

    def _start_run(
        self, started: str, finished: str, eligible: int, analyzed: int, reused: int, failed: int
    ) -> int:
        cursor = self._database.execute(
            """
            INSERT INTO analysis_runs (
                started_at, finished_at, status, eligible, analyzed, reused, failed,
                analysis_schema_version, analyzer_version, config_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                started,
                finished,
                "failed" if failed else "succeeded",
                eligible,
                analyzed,
                reused,
                failed,
                self._identity.schema_version,
                self._identity.analyzer_version,
                self._identity.config_hash,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an analysis run id")
        return int(cursor.lastrowid)

    def _store_success(
        self, track: Track, run_id: int, payload: Mapping[str, Any], now: str
    ) -> None:
        cursor = self._database.execute(
            """
            INSERT INTO audio_analysis (
                track_id, analysis_run_id, analysis_schema_version, analyzer_version, config_hash,
                input_size_bytes, input_mtime_ns, analysis_status, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'succeeded', ?, ?)
            """,
            (
                track.id,
                run_id,
                self._identity.schema_version,
                self._identity.analyzer_version,
                self._identity.config_hash,
                track.size_bytes,
                track.mtime_ns,
                canonical_json(payload),
                now,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an analysis id")
        self._event(
            track.id, run_id, "analysis_completed", {"analysis_id": int(cursor.lastrowid)}, now
        )

    def _store_failure(self, track: Track, run_id: int, error: str, now: str) -> None:
        self._database.execute(
            """
            INSERT OR IGNORE INTO audio_analysis (
                track_id, analysis_run_id, analysis_schema_version, analyzer_version, config_hash,
                input_size_bytes, input_mtime_ns, analysis_status, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'failed', ?, ?)
            """,
            (
                track.id,
                run_id,
                self._identity.schema_version,
                self._identity.analyzer_version,
                self._identity.config_hash,
                track.size_bytes,
                track.mtime_ns,
                canonical_json({"error": error}),
                now,
            ),
        )
        self._event(track.id, run_id, "analysis_failed", {"error": error}, now)

    def _event(
        self, track_id: int, run_id: int, event: str, payload: Mapping[str, Any], now: str
    ) -> None:
        self._database.execute(
            """
            INSERT INTO track_events (
                track_id, occurred_at, analysis_run_id, event_type, payload_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (track_id, now, run_id, event, canonical_json(payload)),
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()
