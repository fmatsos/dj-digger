"""Read and normalize embedded tags through ExifTool."""

import json
import subprocess
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import (
    EmbeddedMetadataRepository,
    EventRepository,
    SourceRepository,
)

EMBEDDED_FIELDS = (
    "Title", "Artist", "AlbumArtist", "Album", "Track", "DiscNumber", "Genre", "Date",
    "Year", "Composer", "Comment", "BPM", "InitialKey", "Grouping",
)


@dataclass(frozen=True)
class EmbeddedMetadata:
    title: str | None = None
    artist: str | None = None
    album_artist: str | None = None
    album: str | None = None
    track_number: str | None = None
    disc_number: str | None = None
    genre: str | None = None
    date: str | None = None
    year: str | None = None
    composer: str | None = None
    comment: str | None = None
    tag_bpm: float | None = None
    tag_initial_key: str | None = None
    grouping: str | None = None


@dataclass(frozen=True)
class ExtractionBatch:
    """Usable metadata and track-local failures from one ExifTool invocation."""

    metadata: dict[int, EmbeddedMetadata]
    failures: dict[int, str]


class ExtractionError(RuntimeError):
    """ExifTool could not produce usable metadata for a requested track."""


class ExifToolExtractor:
    """Read only ExifTool-owned embedded fields with an argv invocation."""

    def __init__(
        self,
        executable: str = "exiftool",
        path_for_track: Callable[[Track], Path] | None = None,
        version: str | None = None,
        timeout_seconds: float = 30.0,
        batch_size: int = 256,
    ) -> None:
        self._executable = executable
        self._has_custom_path_resolver = path_for_track is not None
        self._path_for_track = path_for_track or (lambda track: Path(track.relative_path))
        self._version = version
        self._timeout_seconds = timeout_seconds
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self._batch_size = batch_size

    @property
    def version(self) -> str:
        """Return the cached version reported by the configured ExifTool binary."""
        if self._version is None:
            result = subprocess.run(
                [self._executable, "-ver"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self._timeout_seconds,
            )
            version = result.stdout.strip()
            if not version:
                raise ExtractionError("ExifTool did not report a version")
            self._version = version
        return self._version

    def configure_source_roots(self, roots: Mapping[str, Path]) -> None:
        """Resolve source-relative track identities to current filesystem roots."""
        if self._has_custom_path_resolver:
            return
        self._path_for_track = lambda track: roots[track.source_id] / track.relative_path

    def extract(self, track: Track) -> EmbeddedMetadata:
        """Extract one track, delegating to the same batch-safe implementation."""
        batch = self.extract_many([track])
        if track.id in batch.metadata:
            return batch.metadata[track.id]
        error = batch.failures.get(track.id, "ExifTool returned no metadata for track")
        raise ExtractionError(error)

    def extract_many(self, tracks: list[Track]) -> ExtractionBatch:
        """Read tracks in one ExifTool JSON invocation."""
        if not tracks:
            return ExtractionBatch({}, {})
        metadata: dict[int, EmbeddedMetadata] = {}
        failures: dict[int, str] = {}
        for start in range(0, len(tracks), self._batch_size):
            batch = self._extract_batch(tracks[start : start + self._batch_size])
            metadata.update(batch.metadata)
            failures.update(batch.failures)
        return ExtractionBatch(metadata, failures)

    def _extract_batch(self, tracks: list[Track]) -> ExtractionBatch:
        """Read one argv-safe chunk of tracks."""
        paths = [self._path_for_track(track) for track in tracks]
        argv = [
            self._executable,
            "-json",
            "-charset",
            "filename=UTF8",
            *self._tag_arguments(),
            *(str(path) for path in paths),
        ]
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self._timeout_seconds,
        )
        if not result.stdout.strip():
            raise ExtractionError("ExifTool produced no JSON output")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ExtractionError("ExifTool produced invalid JSON") from error
        if not isinstance(payload, list):
            raise ExtractionError("ExifTool JSON output must be an array")
        by_path: dict[str, deque[Track]] = defaultdict(deque)
        for track, path in zip(tracks, paths, strict=True):
            by_path[str(path)].append(track)
        extracted: dict[int, EmbeddedMetadata] = {}
        failures: dict[int, str] = {}
        for tags in payload:
            if not isinstance(tags, dict) or not isinstance(tags.get("SourceFile"), str):
                continue
            matches = by_path.get(tags["SourceFile"])
            if matches:
                track = matches.popleft()
                if isinstance(tags.get("Error"), str):
                    failures[track.id] = tags["Error"]
                else:
                    extracted[track.id] = self.normalize(tags)
        for track in tracks:
            if track.id not in extracted and track.id not in failures:
                failures[track.id] = "ExifTool returned no metadata for track"
        return ExtractionBatch(extracted, failures)

    def normalize(self, tags: Mapping[str, object]) -> EmbeddedMetadata:
        """Map only explicitly-owned tags and tolerate malformed values."""
        bpm = tags.get("BPM")
        try:
            tag_bpm = float(bpm) if isinstance(bpm, (int, float, str)) and bpm != "" else None
        except (TypeError, ValueError):
            tag_bpm = None
        return EmbeddedMetadata(
            title=_text(tags.get("Title")), artist=_text(tags.get("Artist")),
            album_artist=_text(tags.get("AlbumArtist")), album=_text(tags.get("Album")),
            track_number=_text(tags.get("Track")), disc_number=_text(tags.get("DiscNumber")),
            genre=_text(tags.get("Genre")),
            date=_text(tags.get("Date")),
            year=_text(tags.get("Year")),
            composer=_text(tags.get("Composer")),
            comment=_text(tags.get("Comment")),
            tag_bpm=tag_bpm,
            tag_initial_key=_text(tags.get("InitialKey")), grouping=_text(tags.get("Grouping")),
        )

    @staticmethod
    def _tag_arguments() -> tuple[str, ...]:
        return tuple("-BPM#" if field == "BPM" else f"-{field}" for field in EMBEDDED_FIELDS)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


@dataclass(frozen=True)
class MetadataRunResult:
    extracted: int
    failed: int
    skipped: int

    @property
    def status(self) -> str:
        if self.failed == 0:
            return "succeeded"
        if self.failed > 0 and self.extracted == 0:
            return "failed"
        return "partial"


class MetadataService:
    """Incrementally persist normalized embedded metadata for present tracks."""

    NORMALIZATION_VERSION = "1"

    def __init__(self, database: Database, extractor: ExifToolExtractor) -> None:
        self._database = database
        self._extractor = extractor
        self._metadata = EmbeddedMetadataRepository(database)
        self._events = EventRepository(database)

    def refresh(
        self, source_id: str | None, force: bool = False, path_prefix: str | None = None
    ) -> MetadataRunResult:
        if isinstance(self._extractor, ExifToolExtractor):
            self._extractor.configure_source_roots(SourceRepository(self._database).roots())
        present = self._metadata.present_count(source_id)
        try:
            version = self._extractor.version
        except Exception as error:
            tracks = self._metadata.eligible_tracks(
                source_id,
                extractor_version="",
                normalization_version=self.NORMALIZATION_VERSION,
                force=True,
                path_prefix=path_prefix,
            )
            with self._database.transaction():
                for track in tracks:
                    self._record_failure(track.id, str(error))
            return MetadataRunResult(extracted=0, failed=len(tracks), skipped=0)
        eligible = self._metadata.eligible_tracks(
            source_id,
            extractor_version=version,
            normalization_version=self.NORMALIZATION_VERSION,
            force=force,
            path_prefix=path_prefix,
        )
        if not eligible:
            return MetadataRunResult(extracted=0, failed=0, skipped=present)
        try:
            batch = self._extractor.extract_many(eligible)
        except Exception as error:
            with self._database.transaction():
                for track in eligible:
                    self._record_failure(track.id, str(error))
            return MetadataRunResult(
                extracted=0, failed=len(eligible), skipped=present - len(eligible)
            )
        if isinstance(batch, dict):
            batch = ExtractionBatch(
                batch,
                {
                    track.id: "ExifTool returned no metadata for track"
                    for track in eligible
                    if track.id not in batch
                },
            )
        failures = 0
        succeeded = 0
        with self._database.transaction():
            for track in eligible:
                metadata = batch.metadata.get(track.id)
                if metadata is None:
                    self._record_failure(
                        track.id,
                        batch.failures.get(track.id, "ExifTool returned no metadata for track"),
                    )
                    failures += 1
                    continue
                values = _metadata_values(metadata)
                previous = self._metadata.current(track.id)
                self._metadata.upsert(track, values, extracted_at=_now(), extractor_version=version,
                                      normalization_version=self.NORMALIZATION_VERSION)
                changed = _changed_fields(previous, values)
                if changed:
                    payload = json.dumps({"changed_fields": changed}, separators=(",", ":"))
                    self._events.append(
                        track.id, None, "embedded_metadata_changed", payload, _now()
                    )
                succeeded += 1
        return MetadataRunResult(
            extracted=succeeded, failed=failures, skipped=present - len(eligible)
        )

    def _record_failure(self, track_id: int, error: str) -> None:
        self._events.append(track_id, None, "embedded_metadata_failed",
                            json.dumps({"error": error}, separators=(",", ":")), _now())


def _metadata_values(metadata: EmbeddedMetadata) -> tuple[object, ...]:
    return (
        metadata.title, metadata.artist, metadata.album_artist, metadata.album,
        metadata.track_number, metadata.disc_number, metadata.genre, metadata.date,
        metadata.year, metadata.composer, metadata.comment, metadata.tag_bpm,
        metadata.tag_initial_key, metadata.grouping,
    )


def _changed_fields(previous: tuple[object, ...] | None, current: tuple[object, ...]) -> list[str]:
    names = ("title", "artist", "album_artist", "album", "track_number", "disc_number", "genre",
             "date", "year", "composer", "comment", "tag_bpm", "tag_initial_key", "grouping")
    if previous is None:
        return [name for name, value in zip(names, current, strict=True) if value is not None]
    return [name for name, old, new in zip(names, previous, current, strict=True) if old != new]


def _now() -> str:
    return datetime.now(UTC).isoformat()
