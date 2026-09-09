"""Durability and rollback contract for atomic export publication."""

import os
from pathlib import Path

import pytest

from dj_digger.core.exports.atomic import (
    fsync_directory,
    publish_atomic,
    replace_all_atomically,
)


def _synced_directories(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record every directory whose entry is made durable."""
    synced: list[Path] = []
    real_fsync = os.fsync

    def spy(descriptor: int) -> None:
        try:
            status = os.fstat(descriptor)
        except OSError:  # pragma: no cover - defensive
            status = None
        if status is not None and os.path.stat.S_ISDIR(status.st_mode):
            synced.append(Path(os.readlink(f"/proc/self/fd/{descriptor}")))
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", spy)
    return synced


def test_publish_atomic_makes_the_directory_entry_durable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rename is only durable once its containing directory is synced."""
    synced = _synced_directories(monkeypatch)
    destination = tmp_path / "exports" / "tracks.tsv"

    publish_atomic(destination, lambda path: path.write_text("row\n", encoding="utf-8"))

    assert destination.read_text(encoding="utf-8") == "row\n"
    assert destination.parent.resolve() in [directory.resolve() for directory in synced]


def test_replace_all_atomically_swaps_every_target_and_syncs_each_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    published = tmp_path / "published"
    published.mkdir()
    replacements = []
    for name in ("a.tsv", "b.jsonl"):
        source = staging / name
        source.write_text(f"new {name}\n", encoding="utf-8")
        (published / name).write_text(f"old {name}\n", encoding="utf-8")
        replacements.append((source, published / name))
    synced = _synced_directories(monkeypatch)

    replace_all_atomically(replacements, backup_directory=staging)

    assert (published / "a.tsv").read_text(encoding="utf-8") == "new a.tsv\n"
    assert (published / "b.jsonl").read_text(encoding="utf-8") == "new b.jsonl\n"
    assert published.resolve() in [directory.resolve() for directory in synced]


def test_replace_all_atomically_restores_the_previous_set_when_one_target_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partially applied publication must leave the previous facets intact."""
    staging = tmp_path / "staging"
    staging.mkdir()
    published = tmp_path / "published"
    published.mkdir()
    replacements = []
    for name in ("a.tsv", "b.jsonl"):
        (staging / name).write_text(f"new {name}\n", encoding="utf-8")
        (published / name).write_text(f"old {name}\n", encoding="utf-8")
        replacements.append((staging / name, published / name))

    real_replace = os.replace

    def failing_replace(source: object, target: object) -> None:
        """Refuse only the forward swap of the second staged artifact."""
        if Path(str(source)) == staging / "b.jsonl":
            raise OSError("disk full")
        real_replace(source, target)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError, match="disk full"):
        replace_all_atomically(replacements, backup_directory=staging)

    monkeypatch.undo()
    assert (published / "a.tsv").read_text(encoding="utf-8") == "old a.tsv\n"
    assert (published / "b.jsonl").read_text(encoding="utf-8") == "old b.jsonl\n"


def test_replace_all_atomically_never_masks_the_original_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing best-effort restore must not hide why publication failed."""
    staging = tmp_path / "staging"
    staging.mkdir()
    published = tmp_path / "published"
    published.mkdir()
    (staging / "a.tsv").write_text("new\n", encoding="utf-8")
    (published / "a.tsv").write_text("old\n", encoding="utf-8")

    def always_failing_replace(source: object, target: object) -> None:
        raise OSError("filesystem is read-only")

    monkeypatch.setattr(os, "replace", always_failing_replace)

    with pytest.raises(OSError, match="filesystem is read-only"):
        replace_all_atomically([(staging / "a.tsv", published / "a.tsv")], backup_directory=staging)


def test_replace_all_atomically_rejects_an_unreadable_staged_source(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    published = tmp_path / "published"
    published.mkdir()
    (published / "a.tsv").write_text("old\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        replace_all_atomically(
            [(staging / "missing.tsv", published / "a.tsv")], backup_directory=staging
        )

    assert (published / "a.tsv").read_text(encoding="utf-8") == "old\n"


def test_fsync_directory_tolerates_a_platform_without_directory_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> int:
        raise OSError("directories are not openable here")

    monkeypatch.setattr(os, "open", refuse)

    fsync_directory(tmp_path)
