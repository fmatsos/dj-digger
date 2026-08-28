"""Bounded duplicate detection: fingerprint present tracks and derive groups."""

import time
from collections.abc import Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from dj_digger.analysis.audio import TechnicalAudioMetadata
from dj_digger.analysis.ebur128 import EbuR128Analyzer
from dj_digger.analysis.ffmpeg import FFmpegProbe
from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import TechnicalAudioMetadataRepository
from dj_digger.config import MasteringConfig
from dj_digger.duplicates.fingerprint import (
    FINGERPRINT_VERSION,
    ChromaprintExtractor,
    Fingerprint,
    FingerprintExtractionError,
)
from dj_digger.duplicates.mastering import MASTERING_ANALYSIS_VERSION, MasteringMeasurements
from dj_digger.duplicates.mastering_comparison import MasteringComparison, compare_group
from dj_digger.duplicates.mastering_repository import MasteringRepository
from dj_digger.duplicates.quality import QualityMarkResult, QualitySelector
from dj_digger.duplicates.repository import DuplicateGroup, DuplicateRepository
from dj_digger.progress import NullProgressReporter, ProgressReporter

TECHNICAL_PROBE_VERSION = "ffmpeg-facts/1"

_TECHNICAL_FACT_COLUMNS = (
    "duration_seconds",
    "sample_rate",
    "channels",
    "codec",
    "container",
    "bitrate",
    "lossless",
    "bit_depth",
)


@dataclass(frozen=True)
class DuplicateMemberDescription:
    """One duplicate group member, enriched with technical facts and quality state."""

    source_id: str
    track_id: int
    relative_path: str
    technical_facts: dict[str, object]
    best_quality: bool | None
    audio_analysis: dict[str, float | None] | None = None
    dj_analysis: dict[str, float | None] | None = None
    mastering_comparison: MasteringComparison | None = None


@dataclass(frozen=True)
class DuplicateGroupDescription:
    """A duplicate group identified by its shared fingerprint hash."""

    group_id: str
    members: tuple[DuplicateMemberDescription, ...]
    comparison_status: str = "missing_best_quality"
    analysis_complete: bool = False
    mastering_variant: bool | None = None
    dj_review_recommended: bool | None = None


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
    mastering_files_total: int = 0
    mastering_analyzed: int = 0
    mastering_reused: int = 0
    mastering_failed: int = 0

    @property
    def status(self) -> str:
        if self.failed and self.analyzed == 0 and self.reused == 0:
            return "failed"
        if self.failed or self.mastering_failed:
            return "partial"
        return "succeeded"


class DuplicateService:
    """Fingerprint present tracks and derive duplicate groups from stored hashes."""

    def __init__(
        self,
        database: Database,
        source_roots: Mapping[str, Path],
        *,
        extractor: ChromaprintExtractor | None = None,
        technical_probe: FFmpegProbe | None = None,
        mastering_analyzer: EbuR128Analyzer | None = None,
        mastering_config: MasteringConfig | None = None,
        mastering_repository: MasteringRepository | None = None,
        progress: ProgressReporter | None = None,
    ) -> None:
        self._database = database
        self._source_roots = dict(source_roots)
        self._repository = DuplicateRepository(database)
        self._extractor = extractor or ChromaprintExtractor()
        self._technical_probe = technical_probe or FFmpegProbe()
        self._mastering_analyzer = mastering_analyzer or EbuR128Analyzer()
        self._mastering_repository = mastering_repository or MasteringRepository(database)
        self._mastering_config = mastering_config or MasteringConfig()
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
        mastering: bool = False,
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

            mastering_total = sum(len(group.members) for group in groups) if mastering else 0
            mastering_analyzed = mastering_reused = mastering_failed = 0
            if mastering and groups:
                mastering_analyzed, mastering_reused, mastering_failed = self._analyze_mastering(
                    groups, workers, track_timeout
                )

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
                mastering_files_total=mastering_total,
                mastering_analyzed=mastering_analyzed,
                mastering_reused=mastering_reused,
                mastering_failed=mastering_failed,
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
            track_ids = [member.track.id for member in group.members]
            mastering_rows = self._mastering_repository.current_for_tracks(
                track_ids, MASTERING_ANALYSIS_VERSION
            )
            dj_rows = (
                {
                    int(row[0]): row
                    for row in self._database.execute(
                        "SELECT dj.track_id, dj.required_gain_db, "
                        "dj.available_gain_db, dj.gain_deficit_db "
                        "FROM current_dj_analysis dj JOIN current_mastering_analysis cm "
                        "ON cm.track_id = dj.track_id "
                        "AND cm.mastering_analysis_id = dj.mastering_analysis_id "
                        "JOIN mastering_analysis ma ON ma.id = cm.mastering_analysis_id "
                        "JOIN tracks t ON t.id = cm.track_id "
                        "WHERE cm.analysis_version = ? AND ma.input_size_bytes = t.size_bytes "
                        "AND ma.input_mtime_ns = t.mtime_ns AND dj.track_id IN ("
                        + ",".join("?" for _ in track_ids) + ")",
                        [MASTERING_ANALYSIS_VERSION, *track_ids],
                    ).fetchall()
                }
                if track_ids
                else {}
            )
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
                        audio_analysis=(
                            None
                            if member.track.id not in mastering_rows
                            else {
                                "integrated_lufs": mastering_rows[
                                    member.track.id
                                ].measurements.integrated_lufs,
                                "loudness_range_lu": mastering_rows[
                                    member.track.id
                                ].measurements.loudness_range_lu,
                                "true_peak_dbtp": mastering_rows[
                                    member.track.id
                                ].measurements.true_peak_dbtp,
                                "short_term_lufs_p50": mastering_rows[
                                    member.track.id
                                ].measurements.short_term_lufs_p50,
                                "short_term_lufs_p95": mastering_rows[
                                    member.track.id
                                ].measurements.short_term_lufs_p95,
                                "peak_to_loudness_ratio_db": mastering_rows[
                                    member.track.id
                                ].measurements.peak_to_loudness_ratio_db,
                            }
                        ),
                        dj_analysis=(
                            None
                            if member.track.id not in dj_rows
                            else {
                                "required_gain_db": dj_rows[member.track.id][1],
                                "available_gain_db": dj_rows[member.track.id][2],
                                "gain_deficit_db": dj_rows[member.track.id][3],
                            }
                        ),
                    )
                )
            winner = selections.get((group.members[0].source_id, group.fingerprint_hash))
            comparison_input = []
            for item in members:
                row: dict[str, object] = {"track_id": item.track_id}
                row["_mastering_present"] = item.audio_analysis is not None
                row["_dj_present"] = item.dj_analysis is not None
                if item.audio_analysis:
                    row.update(item.audio_analysis)
                if item.dj_analysis:
                    row.update(item.dj_analysis)
                comparison_input.append(row)
            compared = compare_group(comparison_input, winner, self._mastering_config)
            enriched = tuple(
                DuplicateMemberDescription(
                    **{**item.__dict__, "mastering_comparison": compared.members.get(item.track_id)}
                )
                for item in members
            )
            descriptions.append(
                DuplicateGroupDescription(
                    group.fingerprint_hash,
                    enriched,
                    compared.comparison_status,
                    compared.analysis_complete,
                    compared.mastering_variant,
                    compared.dj_review_recommended,
                )
            )
        return descriptions

    def _analyze_mastering(
        self, groups: list[DuplicateGroup], workers: int, track_timeout: float
    ) -> tuple[int, int, int]:
        tracks = {member.track.id: member.track for group in groups for member in group.members}
        pending: list[Track] = []
        reused = 0
        for track in tracks.values():
            if self._mastering_repository.reusable(track, MASTERING_ANALYSIS_VERSION) is None:
                pending.append(track)
            else:
                reused += 1

        def analyze(
            track: Track,
        ) -> tuple[Track, MasteringMeasurements | None, str | None, str | None]:
            try:
                return (
                    track,
                    self._mastering_analyzer.analyze(self._path_for(track), timeout=track_timeout),
                    None,
                    None,
                )
            except Exception as error:
                stage = getattr(error, "stage", "analysis")
                return track, None, str(stage), str(error)

        analyzed = failed = 0
        iterator = iter(pending)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures: set[
                Future[tuple[Track, MasteringMeasurements | None, str | None, str | None]]
            ] = set()
            for _ in range(workers):
                try:
                    futures.add(executor.submit(analyze, next(iterator)))
                except StopIteration:
                    break
            while futures:
                completed, futures = wait(futures, return_when=FIRST_COMPLETED)
                for future in completed:
                    track, measurements, stage, message = future.result()
                    if measurements is None:
                        self._mastering_repository.persist_failure(
                            track,
                            MASTERING_ANALYSIS_VERSION,
                            stage or "analysis",
                            message or "failed",
                        )
                        failed += 1
                    else:
                        self._mastering_repository.persist_success(
                            track, MASTERING_ANALYSIS_VERSION, measurements
                        )
                        analyzed += 1
                    try:
                        futures.add(executor.submit(analyze, next(iterator)))
                    except StopIteration:
                        pass
        self._mastering_repository.rebuild_dj(
            self._mastering_config.dj_target_lufs,
            self._mastering_config.dj_target_true_peak_dbtp,
        )
        return analyzed, reused, failed

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
