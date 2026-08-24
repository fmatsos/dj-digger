#!/usr/bin/env python3
"""Manual, bounded CIFS acceptance probe.

The mounted path is supplied by ``DJ_DIGGER_CIFS_LIBRARY``.  This probe never
writes below that path and deliberately emits only aggregate, path-redacted
evidence suitable for a manual gate.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    raw = os.environ.get("DJ_DIGGER_CIFS_LIBRARY")
    if not raw:
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "DJ_DIGGER_CIFS_LIBRARY is unset",
                    "archive_created": False,
                }
            )
        )
        return 0
    library = Path(raw)
    if not library.is_dir():
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": "configured library is unavailable",
                    "archive_created": False,
                }
            )
        )
        return 1
    mount_proven = False
    try:
        mount_proven = bool(os.statvfs(library).f_flag & os.ST_RDONLY)
    except OSError:
        mount_proven = False
    if (
        any(shutil.which(binary) is None for binary in ("exiftool", "ffmpeg", "ffprobe"))
        or importlib.util.find_spec("essentia") is None
    ):
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "required dependency unavailable",
                    "bounded_tracks": 0,
                    "archive_created": False,
                }
            )
        )
        return 0
    files = sorted(
        path
        for path in library.rglob("*")
        if path.is_file()
        and path.suffix.lower()
        in {".wav", ".mp3", ".flac", ".aif", ".aiff", ".m4a", ".ogg", ".opus"}
    )
    if not files:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "precondition": "empty library",
                    "archive_created": False,
                }
            )
        )
        return 1
    selected = files[:9]

    def fingerprint() -> str:
        digest = hashlib.sha256()
        for path in selected:
            stat = path.stat()
            digest.update(str(path.relative_to(library)).encode())
            digest.update(str(stat.st_size).encode())
            digest.update(str(stat.st_mtime_ns).encode())
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        return digest.hexdigest()

    before = fingerprint()
    with tempfile.TemporaryDirectory(prefix="dj-digger-cifs-") as workspace:
        staging = Path(workspace) / "staging"
        staging.mkdir()
        for index, source in enumerate(selected):
            (staging / f"{index:02d}{source.suffix}").symlink_to(source)
        (staging / "invalid.wav").write_bytes(b"not-audio")
        config = Path(workspace) / "workspace.toml"
        config.write_text(
            "[workspace]\ndatabase = 'catalog.sqlite'\nexports = 'exports'\n\n"
            "[export]\nlegacy_compatibility = false\n\n"
            "[[library.sources]]\nid = 'cifs'\npath = " + repr(str(staging)) + "\n"
            "set_eligible = true\nanalyze = true\n",
            encoding="utf-8",
        )

        def cli(*args: str) -> tuple[int, dict[str, object]]:
            result = subprocess.run(
                ["python3", "-m", "dj_digger.cli", *args, "--config", str(config)],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            try:
                payload = json.loads(result.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                payload = {}
            return result.returncode, payload

        scan_exit, _ = cli("scan")
        metadata_exit, _ = cli("metadata")
        first_exit, first = cli("analyze", "--limit", "10")
        second_exit, second = cli("analyze", "--limit", "10")
        export_exit, _ = cli("export")
        snapshot_exit, _ = cli(
            "snapshot", "--output", str(Path(workspace) / "snapshot"), "--archive"
        )
        archive_created = (Path(workspace) / "snapshot.tar.gz").is_file()
    unchanged = before == fingerprint()
    partial = first.get("status") == "partial" and second.get("status") == "partial"
    report = {
        "status": (
            "accepted"
            if mount_proven
            and all(
                exit_code == 0
                for exit_code in (scan_exit, metadata_exit, export_exit, snapshot_exit)
            )
            and partial
            and first_exit == 2
            and second_exit == 2
            and second.get("reused", 0) > 0
            and archive_created
            and unchanged
            else "blocked"
        ),
        "bounded_tracks": len(selected),
        "scan_succeeded": scan_exit == 0,
        "metadata_succeeded": metadata_exit == 0,
        "first_analysis_status": first.get("status"),
        "second_analysis_reused": second.get("reused", 0) > 0,
        "partial_analysis_observed": partial,
        "first_analysis_exit_2": first_exit == 2,
        "second_analysis_exit_2": second_exit == 2,
        "exports_succeeded": export_exit == 0,
        "snapshot_succeeded": snapshot_exit == 0,
        "archive_created": archive_created,
        "source_unchanged": unchanged,
        "readonly_mount_proven": mount_proven,
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
