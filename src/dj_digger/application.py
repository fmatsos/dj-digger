"""Application-level orchestration for the DJ Digger command line."""

import importlib.util
import shutil
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from dj_digger.analysis.config import CURRENT_ANALYZER_VERSION, AnalysisIdentity
from dj_digger.analysis.exporters import AnalysisExporter
from dj_digger.analysis.pipeline import (
    AnalysisExtractor,
    AnalysisPipeline,
    AnalysisRunResult,
    TimedAnalysisExtractor,
)
from dj_digger.analysis.worker_client import IsolatedAnalysisExtractor
from dj_digger.catalog.current_analysis import CurrentAnalysisProjector
from dj_digger.catalog.database import Database
from dj_digger.catalog.migrations import CURRENT_VERSION
from dj_digger.catalog.repositories import SourceRepository
from dj_digger.config import LibrarySourceConfig, WorkspaceConfig
from dj_digger.exports.audit import AuditExporter
from dj_digger.exports.snapshot import SnapshotExporter, SnapshotResult
from dj_digger.exports.tracks import TracksExporter
from dj_digger.metadata.exiftool import ExifToolExtractor, MetadataRunResult, MetadataService
from dj_digger.progress import NullProgressReporter, ProgressReporter
from dj_digger.scanning.lifecycle import ScanLifecycle
from dj_digger.scanning.scanner import SourceScanner


@dataclass(frozen=True)
class ScanResult:
    source_id: str
    succeeded: bool
    run_id: int | None
    error: str | None = None


class WorkspaceApplication:
    """Coordinate catalog scanning, metadata, analysis, and publication."""

    def __init__(
        self, config: WorkspaceConfig, *, analysis_extractor: AnalysisExtractor | None = None
    ) -> None:
        self.config = config
        database = Database.open(config.database)
        self.database = database
        try:
            database.migrate()
            self._sources = SourceRepository(database)
            self._analysis_extractor: AnalysisExtractor | TimedAnalysisExtractor
            if analysis_extractor is None:
                self._analysis_identity = AnalysisIdentity(
                    2, CURRENT_ANALYZER_VERSION, config.dsp.config_hash
                )
                self._analysis_extractor = IsolatedAnalysisExtractor(
                    {source.id: source.path for source in config.sources}, config.dsp
                )
            else:
                self._analysis_extractor = analysis_extractor
                self._analysis_identity = getattr(
                    analysis_extractor,
                    "identity",
                    AnalysisIdentity(2, CURRENT_ANALYZER_VERSION, config.dsp.config_hash),
                )
            with database.transaction():
                for source in config.sources:
                    self._sources.upsert(
                        source.id,
                        source.path,
                        set_eligible=source.set_eligible,
                        analyze=source.analyze,
                        enabled=source.enabled,
                    )
        except BaseException:
            database.close()
            raise

    def close(self) -> None:
        """Close the application-owned catalog connection."""
        self.database.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def scan(self, source_id: str | None = None, *, enabled_only: bool = False) -> list[ScanResult]:
        sources = self._selected_sources(source_id, enabled_only=enabled_only)
        lifecycle = ScanLifecycle(self.database)
        scanner = SourceScanner()
        results: list[ScanResult] = []
        for source in sources:
            run_id: int | None = None
            try:
                run_id = lifecycle.begin(source.id)
                observation = scanner.scan(source, run_id)
                lifecycle.observe(run_id, observation)
                lifecycle.succeed(run_id)
            except Exception as error:
                if run_id is not None:
                    try:
                        lifecycle.fail(run_id, "scan", str(error))
                    except Exception:
                        pass
                results.append(ScanResult(source.id, False, run_id, str(error)))
            else:
                results.append(ScanResult(source.id, True, run_id))
        return results

    def metadata(
        self, source_id: str | None = None, *, path_prefix: str | None = None, force: bool = False
    ) -> MetadataRunResult:
        if path_prefix is not None and not path_prefix.strip():
            raise ValueError("path prefix must not be blank")
        return MetadataService(self.database, ExifToolExtractor()).refresh(
            source_id, force=force, path_prefix=path_prefix
        )

    def analyze(
        self,
        source_id: str | None = None,
        *,
        path_prefix: str | None = None,
        limit: int | None = None,
        force: bool = False,
        workers: int = 1,
        track_timeout: float = 1800.0,
        progress: ProgressReporter | None = None,
    ) -> AnalysisRunResult:
        """Run the configured injectable audio analysis extractor."""
        if source_id is not None:
            self._selected_sources(source_id, enabled_only=True)
        return AnalysisPipeline(
            self.database,
            self._analysis_identity,
            self._analysis_extractor,
            progress=progress,
        ).run(
            source_id=source_id,
            path_prefix=path_prefix,
            limit=limit,
            force=force,
            workers=workers,
            track_timeout=track_timeout,
        )

    def export(self, facet: str | None = None) -> list[str]:
        destination = self.config.exports
        destination.mkdir(parents=True, exist_ok=True)
        if facet not in {None, "all", "tracks", "artifacts", "analysis"}:
            raise ValueError(f"unknown export facet: {facet}")
        published: list[str] = []
        # Validate/publish the atomic analysis group first.
        if facet in {"all", "analysis"} or facet is None:
            published.extend(
                str(item.path) for item in AnalysisExporter(self.database).export(destination)
            )
        if facet in {None, "all", "tracks"}:
            tracks = TracksExporter(self.database).export(destination / "tracks.tsv")
            published.append(str(tracks.path))
        if facet in {None, "all", "artifacts"}:
            published.extend(
                str(item.path)
                for item in AuditExporter(self.database).export(destination)
            )
        return published

    def snapshot(self, output: Path, archive: bool) -> SnapshotResult:
        return SnapshotExporter(self.database).create(output, archive)

    def refresh(
        self,
        *,
        workers: int = 1,
        track_timeout: float = 1800.0,
        progress: ProgressReporter | None = None,
    ) -> dict[str, Any]:
        reporter = progress or NullProgressReporter()
        reporter.phase_started("scan", 0, 4)
        scans = self.scan(enabled_only=True)
        reporter.phase_finished("scan", 1, 4)
        eligible = {source.id for source in self.config.sources if source.set_eligible}
        required_failure = any(
            not result.succeeded and result.source_id in eligible for result in scans
        )
        if required_failure:
            return {
                "event": "refresh",
                "status": "failed",
                "published": False,
                "scans": [result.__dict__ for result in scans],
            }
        reporter.phase_started("metadata", 1, 4)
        metadata = self.metadata()
        reporter.phase_finished("metadata", 2, 4)
        reporter.phase_started("analysis", 2, 4)
        analysis = self.analyze(
            workers=workers, track_timeout=track_timeout, progress=reporter
        )
        reporter.phase_finished("analysis", 3, 4)
        status = _worst_status(
            "succeeded" if all(result.succeeded for result in scans) else "partial",
            metadata.status,
            analysis.status,
        )
        reporter.phase_started("exports", 3, 4)
        try:
            exports = self.export()
        except Exception as error:
            reporter.phase_finished("exports", 4, 4)
            return {
                "event": "refresh", "status": "failed", "published": False,
                "error": str(error),
                "scans": [result.__dict__ for result in scans],
                "metadata": metadata.__dict__, "analysis": analysis.__dict__,
            }
        reporter.phase_finished("exports", 4, 4)
        return {
            "event": "refresh",
            "status": status,
            "published": True,
            "scans": [result.__dict__ for result in scans],
            "metadata": metadata.__dict__,
            "analysis": analysis.__dict__,
            "exports": exports,
        }

    def status(self) -> dict[str, Any]:
        sources: list[dict[str, Any]] = []
        for source in self.config.sources:
            present = self.database.scalar(
                "SELECT COUNT(*) FROM tracks WHERE source_id = ? AND presence_status = 'present'",
                (source.id,),
            )
            missing = self.database.scalar(
                "SELECT COUNT(*) FROM tracks WHERE source_id = ? AND presence_status = 'missing'",
                (source.id,),
            )
            latest = self.database.execute(
                "SELECT id, status, finished_at FROM scan_runs WHERE source_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (source.id,),
            ).fetchone()
            sources.append(
                {
                    "source_id": source.id,
                    "enabled": source.enabled,
                    "present_tracks": int(present or 0),
                    "missing_tracks": int(missing or 0),
                    "latest_scan": None
                    if latest is None
                    else {"id": latest[0], "status": latest[1], "finished_at": latest[2]},
                }
            )
        analysis = self.database.execute(
            "SELECT id, status, finished_at, analysis_schema_version, "
            "analyzer_version, config_hash "
            "FROM analysis_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        analysis_identity = (
            None
            if analysis is None
            else {
                "schema_version": analysis[3],
                "analyzer_version": analysis[4],
                "config_hash": analysis[5],
            }
        )
        analysis_facets = {
            name: (self.config.exports / name).is_file()
            for name in ("dj-analysis.tsv", "dj-sections.jsonl", "dj-analysis-run.json")
        }
        return {
            "event": "status",
            "status": "succeeded",
            "sources": sources,
            "latest_analysis": None
            if analysis is None
            else {
                "id": analysis[0],
                "status": analysis[1],
                "finished_at": analysis[2],
                "identity": analysis_identity,
            },
            "exports": {
                "tracks": (self.config.exports / "tracks.tsv").is_file(),
                "analysis": analysis_facets,
            },
        }

    def optimize_database(self) -> dict[str, Any]:
        """Run SQLite's bounded planner-statistics maintenance."""
        self.database.optimize()
        return {"event": "database.optimize", "status": "succeeded"}

    def quick_check_database(self) -> dict[str, Any]:
        """Run the lightweight SQLite consistency check explicitly."""
        result = self.database.quick_check()
        return {
            "event": "database.quick-check",
            "status": "succeeded" if result == "ok" else "failed",
            "quick_check": result,
        }

    def integrity_check_database(self) -> dict[str, Any]:
        """Run SQLite's full integrity check explicitly."""
        results = self.database.integrity_check()
        return {
            "event": "database.integrity-check",
            "status": "succeeded" if results == ["ok"] else "failed",
            "integrity_check": results,
        }

    def rebuild_current_analysis(self) -> dict[str, Any]:
        """Rebuild the derived latest-success projection, then update planner statistics."""
        projected_tracks = CurrentAnalysisProjector(self.database).rebuild()
        self.database.optimize()
        return {
            "event": "database.rebuild-current-analysis",
            "status": "succeeded",
            "projected_tracks": projected_tracks,
        }

    def doctor(self) -> dict[str, Any]:
        issues: list[str] = []
        for source in self.config.sources:
            if not source.path.is_dir():
                issues.append(f"source root unavailable: {source.id} ({source.path})")
        for binary in ("exiftool",):
            if shutil.which(binary) is None:
                issues.append(f"required binary unavailable: {binary}")
        analysis_enabled = any(source.enabled and source.analyze for source in self.config.sources)
        if analysis_enabled:
            for binary in ("ffprobe", "ffmpeg"):
                if shutil.which(binary) is None:
                    issues.append(f"required binary unavailable: {binary}")
            if importlib.util.find_spec("essentia") is None:
                issues.append("required dependency unavailable: essentia")
            if self.config.dsp_path is not None:
                try:
                    from dj_digger.config import DspConfig

                    DspConfig.load(self.config.dsp_path)
                except (OSError, ValueError) as error:
                    issues.append(f"DSP configuration invalid: {error}")
        database = self.database.diagnostics()
        version = int(database["schema_version"])
        expected = CURRENT_VERSION
        if version != expected:
            issues.append(f"SQLite migration version is {version}, expected {expected}")
        if database["journal_mode"] != "wal":
            issues.append(f"SQLite journal mode is {database['journal_mode']}, expected wal")
        if database["foreign_keys"] != 1:
            issues.append("SQLite foreign keys are disabled")
        if database["quick_check"] != "ok":
            issues.append(f"SQLite quick check failed: {database['quick_check']}")
        return {
            "event": "doctor",
            "status": "failed" if issues else "succeeded",
            "database": database["path"],
            "sqlite_version": database["sqlite_version"],
            "migration_version": version,
            "journal_mode": database["journal_mode"],
            "foreign_keys": database["foreign_keys"],
            "synchronous": database["synchronous"],
            "busy_timeout_ms": database["busy_timeout_ms"],
            "database_size_bytes": database["file_size_bytes"],
            "wal_size_bytes": database["wal_size_bytes"],
            "shm_present": database["shm_present"],
            "page_count": database["page_count"],
            "page_size_bytes": database["page_size_bytes"],
            "freelist_count": database["freelist_count"],
            "quick_check": database["quick_check"],
            "issues": issues,
        }

    def _selected_sources(
        self, source_id: str | None, *, enabled_only: bool
    ) -> tuple[LibrarySourceConfig, ...]:
        sources = tuple(
            source for source in self.config.sources if not enabled_only or source.enabled
        )
        if source_id is None:
            return sources
        selected = tuple(source for source in sources if source.id == source_id)
        if not selected:
            raise ValueError(f"unknown or disabled source: {source_id}")
        return selected


def _worst_status(*statuses: str) -> str:
    order = {"succeeded": 0, "partial": 1, "failed": 2}
    return max(statuses, key=lambda status: order.get(status, 2))
