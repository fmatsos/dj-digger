"""Persistence lifecycle for a completed source scan."""

import json
from dataclasses import dataclass

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import (
    ArtifactRepository,
    DirectoryRepository,
    EventRepository,
    ScanRunRepository,
    SourceRepository,
    TrackRepository,
    _now,
)
from dj_digger.scanning.scanner import ScanObservation

SCANNER_VERSION = "0.1.0"


@dataclass(frozen=True)
class ReconciliationResult:
    """Counts reconciled by a successful scan."""

    tracks_missing: int
    directories_missing: int
    artifacts_missing: int


class ScanLifecycle:
    """Persist scan observations and reconcile them only after success."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._sources = SourceRepository(database)
        self._runs = ScanRunRepository(database)
        self._tracks = TrackRepository(database)
        self._directories = DirectoryRepository(database)
        self._artifacts = ArtifactRepository(database)
        self._events = EventRepository(database)

    def begin(self, source_id: str) -> int:
        """Create a running scan for one configured source."""
        return self._runs.start(source_id, scanner_version=SCANNER_VERSION)

    def observe(self, run_id: int, observation: ScanObservation) -> None:
        """Atomically persist positive facts without reconciling absence."""
        with self._database.transaction():
            source_id = self._runs.require_running(run_id)
            if observation.run_id != run_id or observation.source_id != source_id:
                raise ValueError("observation source or run does not match the running scan")
            now = _now()
            for relative_path, audio in observation.audio_paths.items():
                transition = self._tracks.observe(
                    source_id, run_id, relative_path, audio.size_bytes, audio.mtime_ns, now
                )
                if transition.discovered:
                    self._events.append(transition.track_id, run_id, "discovered", None, now)
                if transition.restored:
                    self._events.append(transition.track_id, run_id, "restored", None, now)
                if transition.metadata_changed:
                    payload = json.dumps(
                        {"size_bytes": audio.size_bytes, "mtime_ns": audio.mtime_ns}, sort_keys=True
                    )
                    self._events.append(
                        transition.track_id, run_id, "filesystem_metadata_changed", payload, now
                    )
            for relative_path in observation.directory_paths:
                self._directories.observe(source_id, run_id, relative_path, now)
            for relative_path, artifact in observation.artifacts.items():
                self._artifacts.observe(
                    source_id,
                    run_id,
                    relative_path,
                    artifact.type,
                    artifact.size_bytes,
                    artifact.mtime_ns,
                    now,
                )
            self._runs.update_counters(
                run_id, observation.files_seen, observation.audio_seen, observation.artifacts_seen
            )

    def succeed(self, run_id: int) -> ReconciliationResult:
        """Atomically reconcile a running scan and mark it successful."""
        with self._database.transaction():
            source_id = self._runs.require_running(run_id)
            now = _now()
            missing_track_ids = self._tracks.mark_missing_not_seen(source_id, run_id, now)
            artifacts_missing = self._artifacts.mark_missing_not_seen(source_id, run_id, now)
            directories_missing = self._directories.mark_missing_not_seen(source_id, run_id, now)
            for track_id in missing_track_ids:
                self._events.append(track_id, run_id, "missing", None, now)
            self._runs.mark_succeeded(run_id, now)
            self._sources.set_last_successful_scan(source_id, run_id, now)
        return ReconciliationResult(len(missing_track_ids), directories_missing, artifacts_missing)

    def fail(self, run_id: int, stage: str, error: str) -> None:
        """Terminally fail a running scan without changing catalog presence."""
        with self._database.transaction():
            self._runs.require_running(run_id)
            self._runs.mark_failed(run_id, stage, error, _now())
