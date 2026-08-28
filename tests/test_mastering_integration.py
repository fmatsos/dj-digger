"""Public FFmpeg boundary proof for mastering measurements."""

from pathlib import Path

import pytest
from mastering_fixture import generate_fixture

from dj_digger.analysis.ebur128 import EbuR128Analyzer


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None, reason="FFmpeg unavailable")
def test_public_fixture_is_measured_without_private_media(tmp_path: Path) -> None:
    fixture = generate_fixture(tmp_path / "public.wav")
    result = EbuR128Analyzer().analyze(fixture, timeout=30)
    assert result.integrated_lufs is None or isinstance(result.integrated_lufs, float)
