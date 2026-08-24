"""Opt-in Docker runtime smoke test for the reproducible analysis image."""

import os
import shutil
import subprocess
import wave
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.environ.get("DJ_DIGGER_DOCKER_SMOKE") != "1" or shutil.which("docker") is None,
    reason="set DJ_DIGGER_DOCKER_SMOKE=1 with Docker installed to run the image smoke test",
)
def test_docker_image_reads_synthetic_audio_from_read_only_music_mount(tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    audio = music / "tone.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(48_000)
        stream.writeframes(b"\0\0" * 48_000)
    config = tmp_path / "config.toml"
    config.write_text(
        "[workspace]\n"
        'database = "/workspace/catalog.sqlite"\n'
        'exports = "/workspace/exports"\n\n'
        "[[library.sources]]\n"
        'id = "music"\npath = "/music"\n'
        "set_eligible = true\nanalyze = true\nenabled = true\n",
        encoding="utf-8",
    )
    initial_bytes = audio.read_bytes()

    built = subprocess.run(
        ["docker", "compose", "build", "dj-digger"],
        check=False,
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stderr

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "docker", "compose", "run", "--rm", "--no-deps",
                "--entrypoint", "dj-digger", "-v", f"{tmp_path}:/smoke:ro",
                "-v", f"{music}:/music:ro", "dj-digger", *args,
            ],
            check=False,
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
        )

    doctor = run("doctor", "--config", "/smoke/config.toml")
    assert doctor.returncode == 0, doctor.stderr
    assert '"event":"doctor"' in doctor.stdout
    scan = run("scan", "--config", "/smoke/config.toml")
    assert scan.returncode == 0, scan.stderr
    assert '"event":"scan"' in scan.stdout
    metadata = run("metadata", "--config", "/smoke/config.toml")
    assert metadata.returncode == 0, metadata.stderr
    assert '"event":"metadata"' in metadata.stdout
    assert '"extracted":1' in metadata.stdout
    assert audio.read_bytes() == initial_bytes

    analysis = subprocess.run(
        [
            "docker", "compose", "run", "--rm", "--no-deps", "--entrypoint", "python",
            "-v", f"{tmp_path}:/smoke:ro", "-v", f"{music}:/music:ro",
            "-v", f"{Path(__file__).parents[1]}:/repo:ro", "dj-digger",
            "/repo/tests/docker_analysis_smoke.py", "/smoke/music/tone.wav", "/repo",
        ],
        check=False,
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
    )
    assert analysis.returncode == 0, analysis.stderr
    assert '"status": "succeeded"' in analysis.stdout
    assert audio.read_bytes() == initial_bytes
