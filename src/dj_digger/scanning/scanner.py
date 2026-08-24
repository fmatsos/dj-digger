"""One-pass, read-only discovery of configured music-library sources."""

import os
from dataclasses import dataclass
from pathlib import Path

from dj_digger.artifacts.discovery import classify_dj_artifact
from dj_digger.config import LibrarySourceConfig
from dj_digger.scanning.classifiers import EntryKind, classify


@dataclass(frozen=True)
class AudioObservation:
    """Filesystem facts for one supported audio file."""

    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class ArtifactObservation:
    """Filesystem facts for one supported DJ metadata artifact."""

    type: str
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class ScanObservation:
    """Positive facts collected during one successful source traversal."""

    source_id: str
    run_id: int
    audio_paths: dict[str, AudioObservation]
    directory_paths: set[str]
    artifacts: dict[str, ArtifactObservation]
    files_seen: int

    @property
    def audio_count(self) -> int:
        return len(self.audio_paths)

    @property
    def directory_count(self) -> int:
        return len(self.directory_paths)

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)

    @property
    def audio_seen(self) -> int:
        return self.audio_count

    @property
    def artifacts_seen(self) -> int:
        return self.artifact_count


class SourceScanner:
    """Collect source facts using exactly one recursive filesystem traversal."""

    def scan(self, source: LibrarySourceConfig, run_id: int) -> ScanObservation:
        """Observe a configured source without opening or modifying its files."""
        root = source.path.resolve()
        if not root.is_dir():
            raise ValueError(f"source root is not a directory: {source.path}")

        audio_paths: dict[str, AudioObservation] = {}
        directory_paths: set[str] = set()
        artifacts: dict[str, ArtifactObservation] = {}
        files_seen = 0
        pending = [root]

        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    relative = path.relative_to(root)
                    relative_path = relative.as_posix()
                    if entry.is_dir(follow_symlinks=False):
                        directory_paths.add(relative_path)
                        pending.append(path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    files_seen += 1

                    kind = classify(relative, is_dir=False)
                    if kind is EntryKind.OTHER:
                        continue
                    stat = entry.stat(follow_symlinks=False)
                    if kind is EntryKind.AUDIO:
                        audio_paths[relative_path] = AudioObservation(
                            stat.st_size, stat.st_mtime_ns
                        )
                        continue
                    artifact_type = classify_dj_artifact(relative)
                    if artifact_type is not None:
                        artifacts[relative_path] = ArtifactObservation(
                            artifact_type, stat.st_size, stat.st_mtime_ns
                        )

        return ScanObservation(
            source.id, run_id, audio_paths, directory_paths, artifacts, files_seen
        )
