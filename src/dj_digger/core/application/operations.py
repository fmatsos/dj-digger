"""Typed operational use cases for workspace health and maintenance."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from dj_digger.core.catalog.current_analysis import CurrentAnalysisProjector
from dj_digger.core.catalog.database import Database
from dj_digger.core.catalog.migrations import CURRENT_VERSION
from dj_digger.core.config import WorkspaceConfig

OperationStatus = Literal["succeeded", "partial", "failed"]


@dataclass(frozen=True)
class StatusResult:
    """Current source, analysis, and publication state."""

    sources: tuple[dict[str, Any], ...]
    latest_analysis: dict[str, Any] | None
    exports: dict[str, Any]
    status: OperationStatus = "succeeded"
    event: str = "status"

    def as_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "status": self.status,
            "sources": [dict(source) for source in self.sources],
            "latest_analysis": None if self.latest_analysis is None else dict(self.latest_analysis),
            "exports": dict(self.exports),
        }


@dataclass(frozen=True)
class DoctorResult:
    """Workspace and SQLite diagnostics, including actionable issues."""

    database: str
    sqlite_version: str
    migration_version: int
    journal_mode: str
    foreign_keys: int
    synchronous: int
    busy_timeout_ms: int
    database_size_bytes: int
    wal_size_bytes: int
    shm_present: bool
    page_count: int
    page_size_bytes: int
    freelist_count: int
    quick_check: str
    issues: tuple[str, ...]
    status: OperationStatus = "succeeded"
    event: str = "doctor"

    def as_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "status": self.status,
            "database": self.database,
            "sqlite_version": self.sqlite_version,
            "migration_version": self.migration_version,
            "journal_mode": self.journal_mode,
            "foreign_keys": self.foreign_keys,
            "synchronous": self.synchronous,
            "busy_timeout_ms": self.busy_timeout_ms,
            "database_size_bytes": self.database_size_bytes,
            "wal_size_bytes": self.wal_size_bytes,
            "shm_present": self.shm_present,
            "page_count": self.page_count,
            "page_size_bytes": self.page_size_bytes,
            "freelist_count": self.freelist_count,
            "quick_check": self.quick_check,
            "issues": list(self.issues),
        }


@dataclass(frozen=True)
class DatabaseOptimizeResult:
    event: str = "database.optimize"
    status: OperationStatus = "succeeded"

    def as_dict(self) -> dict[str, Any]:
        return {"event": self.event, "status": self.status}


@dataclass(frozen=True)
class DatabaseQuickCheckResult:
    quick_check: str
    status: OperationStatus
    event: str = "database.quick-check"

    def as_dict(self) -> dict[str, Any]:
        return {"event": self.event, "quick_check": self.quick_check, "status": self.status}


@dataclass(frozen=True)
class DatabaseIntegrityCheckResult:
    integrity_check: tuple[str, ...]
    status: OperationStatus
    event: str = "database.integrity-check"

    def as_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "integrity_check": list(self.integrity_check),
            "status": self.status,
        }


@dataclass(frozen=True)
class DatabaseRebuildResult:
    projected_tracks: int
    event: str = "database.rebuild-current-analysis"
    status: OperationStatus = "succeeded"

    def as_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "projected_tracks": self.projected_tracks,
            "status": self.status,
        }


class StatusUseCase:
    """Read source freshness and catalog publication state."""

    def __init__(self, database: Database, config: WorkspaceConfig) -> None:
        self._database = database
        self._config = config

    def execute(self) -> StatusResult:
        sources: list[dict[str, Any]] = []
        for source in self._config.sources:
            present = self._database.scalar(
                "SELECT COUNT(*) FROM tracks WHERE source_id = ? AND presence_status = 'present'",
                (source.id,),
            )
            missing = self._database.scalar(
                "SELECT COUNT(*) FROM tracks WHERE source_id = ? AND presence_status = 'missing'",
                (source.id,),
            )
            latest = self._database.execute(
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
        analysis = self._database.execute(
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
            name: (self._config.exports / name).is_file()
            for name in ("dj-analysis.tsv", "dj-sections.jsonl", "dj-analysis-run.json")
        }
        return StatusResult(
            tuple(sources),
            None
            if analysis is None
            else {
                "id": analysis[0],
                "status": analysis[1],
                "finished_at": analysis[2],
                "identity": analysis_identity,
            },
            {
                "tracks": (self._config.exports / "tracks.tsv").is_file(),
                "analysis": analysis_facets,
            },
        )


class DoctorUseCase:
    """Check workspace tools and SQLite runtime health."""

    def __init__(
        self,
        database: Database,
        config: WorkspaceConfig,
        *,
        chromaprint_check: Callable[[], bool] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        find_spec: Callable[[str], Any] = importlib.util.find_spec,
    ) -> None:
        self._database = database
        self._config = config
        self._chromaprint_check = chromaprint_check or has_chromaprint_muxer
        self._which = which
        self._find_spec = find_spec

    def execute(self) -> DoctorResult:
        issues: list[str] = []
        for source in self._config.sources:
            if not source.path.is_dir():
                issues.append(f"source root unavailable: {source.id} ({source.path})")
        if self._which("exiftool") is None:
            issues.append("required binary unavailable: exiftool")
        analysis_enabled = any(source.enabled and source.analyze for source in self._config.sources)
        duplicates_expected = any(source.enabled for source in self._config.sources)
        ffmpeg_available = self._which("ffmpeg") is not None
        if analysis_enabled or duplicates_expected:
            for binary in ("ffprobe", "ffmpeg"):
                if self._which(binary) is None:
                    issues.append(f"required binary unavailable: {binary}")
        if analysis_enabled:
            if self._find_spec("essentia") is None:
                issues.append("required dependency unavailable: essentia")
            if self._config.dsp_path is not None:
                try:
                    from dj_digger.core.config import DspConfig

                    DspConfig.load(self._config.dsp_path)
                except (OSError, ValueError) as error:
                    issues.append(f"DSP configuration invalid: {error}")
        if duplicates_expected and ffmpeg_available and not self._chromaprint_check():
            issues.append("ffmpeg is missing the chromaprint muxer required for duplicates")
        diagnostics = self._database.diagnostics()
        version = int(diagnostics["schema_version"])
        if version != CURRENT_VERSION:
            issues.append(f"SQLite migration version is {version}, expected {CURRENT_VERSION}")
        if diagnostics["journal_mode"] != "wal":
            issues.append(f"SQLite journal mode is {diagnostics['journal_mode']}, expected wal")
        if diagnostics["foreign_keys"] != 1:
            issues.append("SQLite foreign keys are disabled")
        if diagnostics["quick_check"] != "ok":
            issues.append(f"SQLite quick check failed: {diagnostics['quick_check']}")
        return DoctorResult(
            database=str(diagnostics["path"]),
            sqlite_version=str(diagnostics["sqlite_version"]),
            migration_version=version,
            journal_mode=str(diagnostics["journal_mode"]),
            foreign_keys=int(diagnostics["foreign_keys"]),
            synchronous=int(diagnostics["synchronous"]),
            busy_timeout_ms=int(diagnostics["busy_timeout_ms"]),
            database_size_bytes=int(diagnostics["file_size_bytes"]),
            wal_size_bytes=int(diagnostics["wal_size_bytes"]),
            shm_present=bool(diagnostics["shm_present"]),
            page_count=int(diagnostics["page_count"]),
            page_size_bytes=int(diagnostics["page_size_bytes"]),
            freelist_count=int(diagnostics["freelist_count"]),
            quick_check=str(diagnostics["quick_check"]),
            issues=tuple(issues),
            status="failed" if issues else "succeeded",
        )


class OptimizeDatabaseUseCase:
    def __init__(self, database: Database) -> None:
        self._database = database

    def execute(self) -> DatabaseOptimizeResult:
        self._database.optimize()
        return DatabaseOptimizeResult()


class QuickCheckDatabaseUseCase:
    def __init__(self, database: Database) -> None:
        self._database = database

    def execute(self) -> DatabaseQuickCheckResult:
        result = self._database.quick_check()
        return DatabaseQuickCheckResult(result, "succeeded" if result == "ok" else "failed")


class IntegrityCheckDatabaseUseCase:
    def __init__(self, database: Database) -> None:
        self._database = database

    def execute(self) -> DatabaseIntegrityCheckResult:
        results = tuple(self._database.integrity_check())
        return DatabaseIntegrityCheckResult(
            results, "succeeded" if results == ("ok",) else "failed"
        )


class RebuildCurrentAnalysisUseCase:
    def __init__(self, database: Database) -> None:
        self._database = database

    def execute(self) -> DatabaseRebuildResult:
        projected_tracks = CurrentAnalysisProjector(self._database).rebuild()
        self._database.optimize()
        return DatabaseRebuildResult(projected_tracks)


# Short aliases keep the command vocabulary discoverable without duplicating implementations.
OptimizeUseCase = OptimizeDatabaseUseCase
QuickCheckUseCase = QuickCheckDatabaseUseCase
IntegrityCheckUseCase = IntegrityCheckDatabaseUseCase
DatabaseOptimizeUseCase = OptimizeDatabaseUseCase
DatabaseQuickCheckUseCase = QuickCheckDatabaseUseCase
DatabaseIntegrityCheckUseCase = IntegrityCheckDatabaseUseCase
DatabaseRebuildUseCase = RebuildCurrentAnalysisUseCase


def has_chromaprint_muxer() -> bool:
    """Report whether FFmpeg can mux Chromaprint fingerprints."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-muxers"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return "chromaprint" in result.stdout


__all__ = [
    "DatabaseIntegrityCheckResult",
    "DatabaseIntegrityCheckUseCase",
    "DatabaseOptimizeResult",
    "DatabaseOptimizeUseCase",
    "DatabaseQuickCheckResult",
    "DatabaseQuickCheckUseCase",
    "DatabaseRebuildResult",
    "DatabaseRebuildUseCase",
    "DoctorResult",
    "DoctorUseCase",
    "IntegrityCheckDatabaseUseCase",
    "IntegrityCheckUseCase",
    "OptimizeDatabaseUseCase",
    "OptimizeUseCase",
    "QuickCheckDatabaseUseCase",
    "QuickCheckUseCase",
    "RebuildCurrentAnalysisUseCase",
    "StatusResult",
    "StatusUseCase",
    "has_chromaprint_muxer",
]
