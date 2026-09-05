#!/usr/bin/env python3
"""Run a bounded native end-to-end smoke test using synthetic audio fixtures.

The smoke test deliberately exercises the public CLI and real FFmpeg, ExifTool,
Essentia, SQLite, and Chromaprint integrations.  It emits aggregate evidence
only; temporary paths and fixture metadata never appear in the report.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _run_cli(config: Path, *args: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "dj_digger.cli", *args, "--config", str(config), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    payload: dict[str, Any]
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        payload = {}
    if result.returncode != 0:
        event = payload.get("event", args[0] if args else "command")
        status = payload.get("status", "unknown")
        raise RuntimeError(f"{event} failed ({status})")
    if payload.get("status") not in {"succeeded", "partial"}:
        event = payload.get("event", args[0] if args else "command")
        raise RuntimeError(f"{event} returned an unexpected status")
    return payload


def _generate_audio(path: Path) -> None:
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
            "sine=frequency=440:duration=2",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
    )


def _write_config(path: Path, source: Path) -> None:
    path.write_text(
        "[workspace]\n"
        "database = 'catalog.sqlite'\n"
        "exports = 'exports'\n\n"
        "[[library.sources]]\n"
        "id = 'synthetic'\n"
        f"path = {str(source)!r}\n"
        "set_eligible = true\n"
        "analyze = true\n",
        encoding="utf-8",
    )


def run() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="dj-digger-cloud-") as temporary:
        workspace = Path(temporary)
        library = workspace / "library"
        library.mkdir()
        first = library / "track-a.wav"
        second = library / "track-b.wav"
        _generate_audio(first)
        shutil.copy2(first, second)
        config = workspace / "config.toml"
        _write_config(config, library)

        doctor = _run_cli(config, "doctor")
        refresh = _run_cli(config, "refresh", "--workers", "1", "--track-timeout", "120")
        duplicates = _run_cli(
            config,
            "duplicates",
            "--analyze",
            "--workers",
            "1",
            "--track-timeout",
            "120",
        )
        duplicate_groups = _run_cli(config, "duplicates", "--list")
        _run_cli(config, "export", "--facet", "all")
        database = workspace / "catalog.sqlite"
        exports = workspace / "exports"
        with sqlite3.connect(database) as connection:
            schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            track_count = int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
            fingerprint_count = int(
                connection.execute("SELECT COUNT(*) FROM audio_fingerprints").fetchone()[0]
            )
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        expected_exports = {
            "tracks.tsv",
            "dj-analysis.tsv",
            "dj-sections.jsonl",
            "dj-analysis-run.json",
        }
        missing_exports = sorted(
            name for name in expected_exports if not (exports / name).is_file()
        )
        groups = duplicate_groups.get("groups", [])
        if schema_version != 9 or track_count != 2 or fingerprint_count < 2:
            raise RuntimeError("catalog smoke assertions failed")
        if quick_check != "ok" or missing_exports or not groups:
            raise RuntimeError("publication smoke assertions failed")
        return {
            "status": "accepted",
            "doctor": doctor.get("status"),
            "refresh": refresh.get("status"),
            "duplicates": duplicates.get("status"),
            "schema_version": schema_version,
            "tracks": track_count,
            "fingerprints": fingerprint_count,
            "duplicate_groups": len(groups),
            "exports": len(expected_exports),
            "quick_check": quick_check,
        }


def main() -> int:
    try:
        report = run()
    except (OSError, RuntimeError, subprocess.CalledProcessError):
        # Never echo exception text: subprocess diagnostics can contain the
        # temporary workspace path or generated fixture names.
        print(json.dumps({"status": "failed", "error": "native runtime smoke failed"}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
