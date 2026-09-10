"""Atomic publication helpers.

A ``rename`` only becomes durable once the directory entry that carries it has
been synced, so every helper here fsyncs both the file and its parent directory.
Multi-file publication is not atomic on POSIX: the best available guarantee is
that a failed swap restores the previously published set.
"""

import contextlib
import os
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path


def fsync_directory(path: Path) -> None:
    """Make renames inside ``path`` durable, degrading on platforms without it."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        os.close(descriptor)


def fsync_file(path: Path) -> None:
    """Flush one staged artifact's contents to stable storage."""
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def publish_atomic(destination: Path, writer: Callable[[Path], None]) -> None:
    """Write using writer(path), fsync, then durably replace destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(name)
    try:
        writer(temporary)
        fsync_file(temporary)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    fsync_directory(destination.parent)


def replace_all_atomically(
    replacements: Sequence[tuple[Path, Path]], *, backup_directory: Path
) -> None:
    """Swap staged artifacts into place, restoring the previous set on failure.

    Every staged source is fsynced before any target is touched, so a failure
    while swapping can only be a rename failure — never a half-written file.
    """
    for source, _ in replacements:
        fsync_file(source)
    backups: list[tuple[Path, Path]] = []
    replaced: list[Path] = []
    try:
        for _, target in replacements:
            if target.exists():
                backup = backup_directory / f"{target.name}.bak"
                os.replace(target, backup)
                backups.append((target, backup))
        for source, target in replacements:
            os.replace(source, target)
            replaced.append(target)
    except BaseException:
        # Best effort: a restore that fails too must never mask the original cause.
        for target in replaced:
            with contextlib.suppress(OSError):
                target.unlink(missing_ok=True)
        for target, backup in backups:
            try:
                if backup.exists():
                    os.replace(backup, target)
            except OSError:
                pass
        raise
    for directory in {target.parent for _, target in replacements}:
        fsync_directory(directory)


__all__ = ["fsync_directory", "fsync_file", "publish_atomic", "replace_all_atomically"]
