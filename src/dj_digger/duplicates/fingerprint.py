"""Bounded Chromaprint fingerprint extraction via FFmpeg, never decoding audio in-process."""

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

FINGERPRINT_VERSION = "ffmpeg-chromaprint/1"


class FingerprintExtractionError(Exception):
    """Raised when FFmpeg fails to produce a usable Chromaprint fingerprint."""


@dataclass(frozen=True)
class Fingerprint:
    """A complete base64 Chromaprint fingerprint and its group identifier."""

    fingerprint: str
    fingerprint_hash: str
    fingerprint_version: str


class ChromaprintExtractor:
    """Extract a complete base64 Chromaprint fingerprint without a shell or decoded audio."""

    def __init__(self, ffmpeg: str = "ffmpeg") -> None:
        self._ffmpeg = ffmpeg

    def extract(self, path: Path, *, timeout: float) -> Fingerprint:
        """Run FFmpeg's Chromaprint muxer on one file, bounded by timeout seconds."""
        argv = [
            self._ffmpeg,
            "-v", "error",
            "-i", str(path),
            "-map", "0:a:0",
            "-f", "chromaprint",
            "-algorithm", "1",
            "-fp_format", "base64",
            "-",
        ]
        try:
            result = subprocess.run(argv, check=False, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise FingerprintExtractionError(
                f"chromaprint extraction timed out after {timeout}s for {path}"
            ) from error

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise FingerprintExtractionError(
                f"ffmpeg exited with code {result.returncode} for {path}: {stderr}"
            )

        fingerprint = result.stdout.decode("ascii", errors="replace").strip()
        if not fingerprint:
            raise FingerprintExtractionError(f"empty chromaprint fingerprint for {path}")

        fingerprint_hash = hashlib.sha256(fingerprint.encode("ascii")).hexdigest()
        return Fingerprint(
            fingerprint=fingerprint,
            fingerprint_hash=fingerprint_hash,
            fingerprint_version=FINGERPRINT_VERSION,
        )
