"""Application-level orchestration for the DJ Digger command line."""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dj_digger.catalog.database import Database
from dj_digger.catalog.migrations import MIGRATIONS
from dj_digger.catalog.repositories import SourceRepository
from dj_digger.config import LibrarySourceConfig, WorkspaceConfig
from dj_digger.exports.audit import AuditExporter
from dj_digger.exports.snapshot import SnapshotExporter, SnapshotResult
from dj_digger.exports.tracks import TracksExporter
from dj_digger.metadata.exiftool import ExifToolExtractor, MetadataRunResult, MetadataService
from dj_digger.scanning.lifecycle import ScanLifecycle
from dj_digger.scanning.scanner import SourceScanner


@dataclass(frozen=True)
class ScanResult:
    source_id: str
    succeeded: bool
    run_id: int | None
    error: str | None = None


class WorkspaceApplication:
    """Coordinate existing catalog services without adding analysis orchestration."""

    def __init__(self, config: WorkspaceConfig) -> None:
        self.config = config
        self.database = Database.open(config.database)
        self.database.migrate()
        self._sources = SourceRepository(self.database)
        for source in config.sources:
            self._sources.upsert(
                source.id,
                source.path,
                set_eligible=source.set_eligible,
                analyze=source.analyze,
                enabled=source.enabled,
            )

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

    def export(self, facet: str | None = None) -> list[str]:
        destination = self.config.exports
        destination.mkdir(parents=True, exist_ok=True)
        if facet not in {None, "all", "tracks", "artifacts"}:
            raise ValueError(f"unknown export facet: {facet}")
        published: list[str] = []
        if facet in {None, "all", "tracks"}:
            tracks = TracksExporter(self.database).export(destination / "tracks.tsv")
            published.append(str(tracks.path))
        if facet in {None, "all", "artifacts"}:
            published.extend(
                str(item.path)
                for item in AuditExporter(self.database).export(
                    destination, legacy_compatibility=self.config.export.legacy_compatibility
                )
            )
        return published

    def snapshot(self, output: Path, archive: bool) -> SnapshotResult:
        return SnapshotExporter(self.database).create(output, archive)

    def refresh(self) -> dict[str, Any]:
        scans = self.scan(enabled_only=True)
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
        metadata = self.metadata()
        return {
            "event": "refresh",
            "status": "succeeded",
            "published": True,
            "scans": [result.__dict__ for result in scans],
            "metadata": metadata.__dict__,
            "exports": self.export(),
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
            "SELECT id, status, finished_at FROM analysis_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {
            "event": "status",
            "status": "succeeded",
            "sources": sources,
            "latest_analysis": None
            if analysis is None
            else {"id": analysis[0], "status": analysis[1], "finished_at": analysis[2]},
            "exports": {"tracks": (self.config.exports / "tracks.tsv").is_file()},
        }

    def doctor(self) -> dict[str, Any]:
        issues: list[str] = []
        for source in self.config.sources:
            if not source.path.is_dir():
                issues.append(f"source root unavailable: {source.id} ({source.path})")
        for binary in ("exiftool", "ffprobe", "ffmpeg"):
            if shutil.which(binary) is None:
                issues.append(f"required binary unavailable: {binary}")
        version = int(self.database.scalar("PRAGMA user_version") or 0)
        expected = MIGRATIONS[-1][0]
        if version != expected:
            issues.append(f"SQLite migration version is {version}, expected {expected}")
        return {
            "event": "doctor",
            "status": "failed" if issues else "succeeded",
            "database": str(self.config.database),
            "migration_version": version,
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
