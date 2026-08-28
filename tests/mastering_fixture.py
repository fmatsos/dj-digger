"""Helpers for deterministic public FFmpeg mastering fixtures."""

import subprocess
from pathlib import Path


def generate_fixture(path: Path, *, duration: float = 1.0, gain: float = 1.0) -> Path:
    """Generate a public sine-wave fixture without touching source bytes later."""
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-filter:a",
            f"volume={gain}",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
    )
    return path
