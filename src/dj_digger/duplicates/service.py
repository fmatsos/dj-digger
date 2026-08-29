"""Bounded duplicate detection: fingerprint present tracks and derive groups."""

import time
from collections.abc import Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from dj_digger.analysis.audio import TechnicalAudioMetadata
from dj_digger.analysis.ffmpeg import FFmpegProbe
from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import TechnicalAudioMetadataRepository
from dj_digger.duplicates.fingerprint import (
    FINGERPRINT_VERSION,
    ChromaprintExtractor,
    Fingerprint,
    FingerprintExtractionError,
)
from dj_digger.duplicates.quality import QualityMarkResult, QualitySelector
from dj_digger.duplicates.repository import DuplicateGroup, DuplicateRepository
from dj_digger.progress import NullProgressReporter, ProgressReporter

TECHNICAL_PROBE_VERSION = "ffmpeg-facts/1"

_TECHNICAL_FACT_COLUMNS = (
    "duration_seconds", "sample_rate", "channels", "codec", "container", "bitrate",
    "lossless", "bit_depth",
)


@dataclass(frozen=True)
class DuplicateMemberDescription:
    """One duplicate group member, enriched with technical facts and quality state."""

    source_id: str
    track_id: int
    relative_path: str
    technical_facts: dict[str, object]
    best_quality: bool | None


@dataclass(frozen=True)
class DuplicateGroupDescription:
    """A duplicate group identified by its shared fingerprint hash."""

    group_id: str
    members: tuple[DuplicateMemberDescription, ...]


@dataclass(frozen=True)
class DuplicateAnalysisResult:
    """Counters for one duplicate analysis pass."""

    files_total: int
    analyzed: int
    reused: int
    failed: int
    duplicate_files: int
    duplicate_groups: int
    elapsed_seconds: float
    marked_best: int = 0


class DuplicateService:
    """Fingerprint present tracks and derive duplicate groups from stored hashes."""

    def __init__(
        self,
        database: Database,
        source_roots: Mapping[str, Path],
        *,
        extractor: ChromaprintExtractor | None = None,
        technical_probe: FFmpegProbe | None = None,
        progress: ProgressReporter | None = None,
    ) -> None:
        self._database = database
        self._source_roots = dict(source_roots)
        self._repository = DuplicateRepository(database)
        self._extractor = extractor or ChromaprintExtractor()
        self._technical_probe = technical_probe or FFmpegProbe()
        self._technical_repository = TechnicalAudioMetadataRepository(database)
        self._progress = progress or NullProgressReporter()
        self._quality = QualitySelector(database)

    def _path_for(self, track: Track) -> Path:
        return self._source_roots[track.source_id] / track.relative_path

    def analyze(
        self,
        *,
        source_id: str | None = None,
        workers: int = 1,
        track_timeout: float = 1800.0,
        mark_best_quality: bool = False,
    ) -> DuplicateAnalysisResult:
        """Fingerprint present tracks in the requested scope, reusing current results."""
        with self._database.advisory_lock("duplicates"):
            if workers < 1:
                raise ValueError("workers must be positive")
            if not isfinite(track_timeout) or track_timeout <= 0:
                raise ValueError("track timeout must be positive")

            started = time.monotonic()
            tracks = self._repository.present_tracks(source_id)
            reused_ids: set[int] = set()
            pending: list[Track] = []
            for track in tracks:
                if self._repository.reusable_fingerprint(track, FINGERPRINT_VERSION) is not None:
                    reused_ids.add(track.id)
                else:
                    pending.append(track)

            self._progress.analysis_started(total=len(tracks), completed=len(reused_ids))
            try:
                analyzed, failed = self._extract_all(pending, workers, track_timeout)
            finally:
                self._progress.analysis_finished()

            with self._database.transaction():
                self._repository.invalidate_stale_quality_selections()
            groups = self._repository.groups(source_id)

            marked_best = 0
            if mark_best_quality and failed == 0:
                mark_result = self._quality.mark_best_quality(source_id)
                if mark_result.status == "succeeded":
                    marked_best = mark_result.marked_best

            return DuplicateAnalysisResult(
                files_total=len(tracks),
                analyzed=analyzed,
                reused=len(reused_ids),
                failed=failed,
                duplicate_files=sum(len(group.members) for group in groups),
                duplicate_groups=len(groups),
                elapsed_seconds=time.monotonic() - started,
                marked_best=marked_best,
            )

    def groups(self, source_id: str | None = None) -> list[DuplicateGroup]:
        """Return duplicate groups of at least two present tracks, in deterministic order."""
        return self._repository.groups(source_id)

    def mark_best_quality(self, source_id: str | None = None) -> QualityMarkResult:
        """Elect and persist the best-quality track per duplicate group, standalone."""
        return self._quality.mark_best_quality(source_id)

    def describe_groups(self, source_id: str | None = None) -> list[DuplicateGroupDescription]:
        """Return duplicate groups enriched with technical facts and quality state."""
        groups = self._repository.groups(source_id)
        selections = self._repository.quality_selections(source_id)
        descriptions: list[DuplicateGroupDescription] = []
        for group in groups:
            members = []
            for member in group.members:
                winner = selections.get((member.source_id, group.fingerprint_hash))
                best_quality = None if winner is None else winner == member.track.id
                members.append(
                    DuplicateMemberDescription(
                        source_id=member.source_id,
                        track_id=member.track.id,
                        relative_path=member.track.relative_path,
                        technical_facts=self._technical_facts(member.track.id),
                        best_quality=best_quality,
                    )
                )
            descriptions.append(DuplicateGroupDescription(group.fingerprint_hash, tuple(members)))
        return descriptions

    def _technical_facts(self, track_id: int) -> dict[str, object]:
        row = self._database.execute(
            f"SELECT {', '.join(_TECHNICAL_FACT_COLUMNS)} "
            "FROM technical_audio_metadata WHERE track_id = ?",
            (track_id,),
        ).fetchone()
        if row is None:
            return dict.fromkeys(_TECHNICAL_FACT_COLUMNS)
        facts = dict(zip(_TECHNICAL_FACT_COLUMNS, row, strict=True))
        if facts["lossless"] is not None:
            facts["lossless"] = bool(facts["lossless"])
        return facts

    def _extract_all(
        self, tracks: list[Track], workers: int, track_timeout: float
    ) -> tuple[int, int]:
        Outcome = tuple[Track, Fingerprint | None, TechnicalAudioMetadata | None, str | None]

        def extract(track: Track) -> Outcome:
            path = self._path_for(track)
            try:
                fingerprint = self._extractor.extract(path, timeout=track_timeout)
            except FingerprintExtractionError as error:
                return track, None, None, str(error)
            try:
                facts = self._technical_probe.probe_facts(path)
            except Exception:
                facts = None
            return track, fingerprint, facts, None

        analyzed = 0
        failed = 0
        tracks_iterator = iter(tracks)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures: set[Future[Outcome]] = set()
            for _ in range(workers):
                try:
                    track = next(tracks_iterator)
                except StopIteration:
                    break
                futures.add(executor.submit(extract, track))

            while futures:
                completed, futures = wait(futures, return_when=FIRST_COMPLETED)
                for future in completed:
                    track, fingerprint, facts, error = future.result()
                    if fingerprint is not None:
                        with self._database.transaction():
                            self._repository.upsert_fingerprint(track, fingerprint)
                            if facts is not None:
                                self._technical_repository.upsert_facts(
                                    track, facts, TECHNICAL_PROBE_VERSION
                                )
                        analyzed += 1
                    else:
                        failed += 1
                        self._progress.diagnostic("error", f"{track.relative_path}: {error}")
                    self._progress.analysis_advanced()
                    try:
                        next_track = next(tracks_iterator)
                    except StopIteration:
                        continue
                    futures.add(executor.submit(extract, next_track))
        return analyzed, failed
