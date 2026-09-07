"""Metadata command adapter."""

from pathlib import Path
from typing import Any

from dj_digger.cli.runtime import run_metadata


def execute(
    config: Path,
    source: str | None,
    path: str | None,
    force: bool,
) -> dict[str, Any]:
    """Execute metadata refresh through the core boundary."""
    return run_metadata(config, source, path, force)
