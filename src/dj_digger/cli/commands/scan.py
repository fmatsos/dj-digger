"""Scan command adapter."""

from pathlib import Path
from typing import Any

from dj_digger.cli.runtime import run_scan


def execute(config: Path, source: str | None) -> dict[str, Any]:
    """Execute scan through the core boundary."""
    return run_scan(config, source)
