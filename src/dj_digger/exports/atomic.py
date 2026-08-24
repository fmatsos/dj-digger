"""Atomic publication helpers."""

import os
import tempfile
from collections.abc import Callable
from pathlib import Path


def publish_atomic(destination: Path, writer: Callable[[Path], None]) -> None:
    """Write using writer(path), fsync, then replace destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(name)
    try:
        writer(temporary)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
