"""Shared pytest configuration and dependency markers."""

import shutil

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Classify integration tests and gate tests requiring FFmpeg."""
    ffmpeg_missing = shutil.which("ffmpeg") is None
    skip_ffmpeg = pytest.mark.skip(reason="FFmpeg is not installed")
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)
        if ffmpeg_missing and "requires_ffmpeg" in item.keywords:
            item.add_marker(skip_ffmpeg)
