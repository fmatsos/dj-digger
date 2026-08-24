"""Bounded, deterministic orchestration for immutable audio analysis attempts."""

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.analysis.eligibility import AnalysisEligibility
from dj_digger.analysis.extractor import AnalysisExtractionError, Stage
from dj_digger.analysis.persistence import AnalysisOutcome, AnalysisPersistence
from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import TrackRepository

AnalysisExtractor = Callable[[Track], Mapping[str, Any]]
_STAGES = frozenset(
    {
        "decode", "technical", "rhythm", "spectrum", "windows", "segmentation", "semantics",
        "aggregation",
    }
)


@dataclass(frozen=True)
class AnalysisRunResult:
    """Counters for one aggregate analysis run."""

    run_id: int
    eligible: int
    analyzed: int
    reused: int
    failed: int
    status: str = "succeeded"


class AnalysisPipeline:
    """Compute independent tracks concurrently and persist them serially."""

    def __init__(
        self, database: Database, identity: AnalysisIdentity, extract: AnalysisExtractor
    ) -> None:
        self._database = database
        self._identity = identity
        self._extract = extract
        self._tracks = TrackRepository(database)
        self._persistence = AnalysisPersistence(database)

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
        run_id, analyzed, failed = self._persistence.persist_run(
            self._identity,
            outcomes,
            eligible=len(selected),
            reused=len(reusable),
            started_at=started,
            finished_at=finished,
        )
        status = "succeeded" if failed == 0 else ("failed" if analyzed == 0 else "partial")
        return AnalysisRunResult(run_id, len(selected), analyzed, len(reusable), failed, status)

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
    ) -> list[AnalysisOutcome]:
        def extract(track: Track) -> AnalysisOutcome:
            try:
                return AnalysisOutcome(track, self._extract(track), None, "aggregation")
            except Exception as error:
                stage: Stage = "aggregation"
                if isinstance(error, AnalysisExtractionError) and error.stage in _STAGES:
                    stage = error.stage
                return AnalysisOutcome(track, {}, str(error), stage)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(extract, tracks))

def _now() -> str:
    return datetime.now(UTC).isoformat()
