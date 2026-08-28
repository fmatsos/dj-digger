import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from dj_digger.duplicates.fingerprint import (
    FINGERPRINT_VERSION,
    ChromaprintExtractor,
    FingerprintExtractionError,
)


def _fake_result(*, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> object:
    return type(
        "Result", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr}
    )()


def test_extract_invokes_ffmpeg_without_a_shell(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(argv: list[str], **kwargs: object) -> object:
        calls.append((argv, kwargs))
        return _fake_result(stdout=b"AQAAAA")

    monkeypatch.setattr("dj_digger.duplicates.fingerprint.subprocess.run", run)
    path = Path("odd;name\\n.flac")

    result = ChromaprintExtractor().extract(path, timeout=30)

    assert result.fingerprint == "AQAAAA"
    assert result.fingerprint_version == FINGERPRINT_VERSION
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [
        "ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0",
        "-f", "chromaprint", "-algorithm", "1", "-fp_format", "base64", "-",
    ]
    assert kwargs.get("timeout") == 30
    assert "shell" not in kwargs


def test_extract_returns_a_stable_sha256_group_hash(monkeypatch) -> None:
    monkeypatch.setattr(
        "dj_digger.duplicates.fingerprint.subprocess.run",
        lambda argv, **kwargs: _fake_result(stdout=b"AQAAG0okqkkq"),
    )

    result = ChromaprintExtractor().extract(Path("track.wav"), timeout=30)

    assert result.fingerprint_hash == hashlib.sha256(b"AQAAG0okqkkq").hexdigest()


def test_extract_raises_on_timeout(monkeypatch) -> None:
    def run(argv: list[str], **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs["timeout"])

    monkeypatch.setattr("dj_digger.duplicates.fingerprint.subprocess.run", run)

    with pytest.raises(FingerprintExtractionError, match="timed out"):
        ChromaprintExtractor().extract(Path("track.wav"), timeout=5)


def test_extract_raises_on_empty_fingerprint(monkeypatch) -> None:
    monkeypatch.setattr(
        "dj_digger.duplicates.fingerprint.subprocess.run",
        lambda argv, **kwargs: _fake_result(stdout=b"   \n"),
    )

    with pytest.raises(FingerprintExtractionError, match="empty chromaprint"):
        ChromaprintExtractor().extract(Path("track.wav"), timeout=30)


def test_extract_raises_on_process_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "dj_digger.duplicates.fingerprint.subprocess.run",
        lambda argv, **kwargs: _fake_result(
            returncode=1, stderr=b"Invalid data found when processing input"
        ),
    )

    with pytest.raises(FingerprintExtractionError, match="Invalid data found"):
        ChromaprintExtractor().extract(Path("track.mp3"), timeout=30)


def _require_ffmpeg_chromaprint() -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed; chromaprint extraction is unverified")
    muxers = subprocess.run(
        ["ffmpeg", "-hide_banner", "-muxers"], check=True, capture_output=True, text=True
    ).stdout
    if "chromaprint" not in muxers:
        pytest.skip("ffmpeg lacks the chromaprint muxer; extraction is unverified")


def _generate_signal(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", "aevalsrc=0.4*sin(2*PI*t*(220+220*t)):s=44100:d=6",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_wav_flac_mp3_encodings_of_the_same_signal_fingerprint_identically(
    tmp_path: Path,
) -> None:
    _require_ffmpeg_chromaprint()
    wav_path = tmp_path / "signal.wav"
    flac_path = tmp_path / "signal.flac"
    mp3_path = tmp_path / "signal.mp3"
    _generate_signal(wav_path)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(wav_path), str(flac_path)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(wav_path), "-b:a", "320k", str(mp3_path)],
        check=True, capture_output=True,
    )

    extractor = ChromaprintExtractor()
    wav_result = extractor.extract(wav_path, timeout=30)
    flac_result = extractor.extract(flac_path, timeout=30)
    mp3_result = extractor.extract(mp3_path, timeout=30)

    assert wav_result.fingerprint_hash == flac_result.fingerprint_hash
    assert wav_result.fingerprint_hash == mp3_result.fingerprint_hash


def test_distinct_signals_fingerprint_differently(tmp_path: Path) -> None:
    _require_ffmpeg_chromaprint()
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", "aevalsrc=0.4*sin(2*PI*t*(220+220*t)):s=44100:d=6",
            str(first),
        ],
        check=True, capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", "aevalsrc=0.4*sin(2*PI*t*(880+880*t)):s=44100:d=6",
            str(second),
        ],
        check=True, capture_output=True,
    )

    extractor = ChromaprintExtractor()
    assert extractor.extract(first, timeout=30).fingerprint_hash != extractor.extract(
        second, timeout=30
    ).fingerprint_hash
