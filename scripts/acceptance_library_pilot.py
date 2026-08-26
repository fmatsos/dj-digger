#!/usr/bin/env python3
"""Manual, bounded local-library acceptance probe.

The library path is supplied by ``DJ_DIGGER_LIBRARY_ROOT``.  This probe never
writes below that path and deliberately emits only aggregate, path-redacted
evidence suitable for a manual gate.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path


def _error_category(payload: dict[str, object]) -> str | None:
    """Classify CLI failures without exposing their messages or paths."""
    if payload.get("status") != "failed":
        return None
    raw = str(payload.get("error", "")).lower()
    if "transaction" in raw or "database" in raw or "sqlite" in raw:
        return "database_transaction"
    if any(token in raw for token in ("ffmpeg", "ffprobe", "exiftool", "essentia", "decoder")):
        return "dependency"
    if "schema" in raw or "validation" in raw or "export" in raw:
        return "export_validation"
    if any(token in raw for token in ("nan", "infinite", "inf", "out of range", "non-finite")):
        return "non_finite_analysis"
    if any(token in raw for token in ("json", "serializ", "not serializable")):
        return "serialization"
    if "section" in raw:
        return "section_persistence"
    if any(token in raw for token in ("foreign key", "unique", "not null", "check constraint")):
        return "constraint"
    if any(token in raw for token in ("mapping", "tuple", "object", "typeerror", "type error")):
        return "empty_payload/type_error"
    if "config" in raw or "toml" in raw:
        return "config"
    return "unknown"


def main() -> int:
    raw = os.environ.get("DJ_DIGGER_LIBRARY_ROOT")
    if not raw:
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "DJ_DIGGER_LIBRARY_ROOT is unset",
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
    with tempfile.TemporaryDirectory(prefix="dj-digger-library-") as workspace:
        staging = Path(workspace) / "staging"
        staging.mkdir()
        # The scanner intentionally does not follow file symlinks.  Stage
        # private copies in the writable temp workspace so the source remains
        # untouched while production discovery sees audio files.
        for index, source in enumerate(selected):
            shutil.copy2(source, staging / f"{index:02d}{source.suffix}")
        (staging / "invalid.wav").write_bytes(b"not-audio")
        config = Path(workspace) / "workspace.toml"
        config.write_text(
            "[workspace]\ndatabase = 'catalog.sqlite'\nexports = 'exports'\n\n"
            "[[library.sources]]\nid = 'library'\npath = " + repr(str(staging)) + "\n"
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

        cli_error_categories: dict[str, int] = {}

        def run_cli(*args: str) -> tuple[int, dict[str, object]]:
            exit_code, payload = cli(*args)
            category = _error_category(payload)
            if category is not None:
                cli_error_categories[category] = cli_error_categories.get(category, 0) + 1
            return exit_code, payload

        scan_exit, _ = run_cli("scan")
        metadata_exit, _ = run_cli("metadata")
        first_exit, first = run_cli("analyze", "--limit", "10")
        # Force a complete second selection: successful tracks are otherwise
        # filtered as non-pending before the reuse check can observe them.
        second_exit, second = run_cli("analyze", "--limit", "10", "--force")
        export_exit, _ = run_cli("export")
        snapshot_exit, _ = run_cli(
            "snapshot", "--output", str(Path(workspace) / "snapshot"), "--archive"
        )
        archive_created = (Path(workspace) / "snapshot.tar.gz").is_file()
        analysis_error_stages: dict[str, int] = {}
        database_path = Path(workspace) / "catalog.sqlite"
        with sqlite3.connect(database_path) as database:
            rows = database.execute(
                "SELECT payload_json FROM audio_analysis WHERE analysis_status = 'failed'"
            ).fetchall()
            analysis_runs = int(
                database.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
            )
            analysis_attempts = int(
                database.execute("SELECT COUNT(*) FROM audio_analysis").fetchone()[0]
            )
        for (payload,) in rows:
            try:
                stage = str(json.loads(payload).get("stage", "unknown"))
            except (TypeError, ValueError):
                stage = "unknown"
            analysis_error_stages[stage] = analysis_error_stages.get(stage, 0) + 1
    unchanged = before == fingerprint()
    partial = first.get("status") == "partial" and second.get("status") == "partial"
    report = {
        "status": (
            "accepted"
            if all(
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
        "analysis_error_stages": analysis_error_stages,
        "cli_error_categories": cli_error_categories,
        "analysis_runs": analysis_runs,
        "analysis_attempts": analysis_attempts,
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
