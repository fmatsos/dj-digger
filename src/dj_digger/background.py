"""Detached re-execution and status tracking for long-running CLI commands."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

JOB_ID_ENV = "DJ_DIGGER_JOB_ID"


def jobs_dir(database_path: Path) -> Path:
    return database_path.parent / "jobs"


def _status_path(database_path: Path, job_id: str) -> Path:
    return jobs_dir(database_path) / f"{job_id}.json"


def _log_path(database_path: Path, job_id: str) -> Path:
    return jobs_dir(database_path) / f"{job_id}.log"


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def current_job_id() -> str | None:
    return os.environ.get(JOB_ID_ENV)


def launch(database_path: Path, command: str, argv: list[str]) -> dict[str, Any]:
    """Re-exec this CLI without --background, detached, logging to a file."""
    job_id = uuid4().hex[:12]
    directory = jobs_dir(database_path)
    directory.mkdir(parents=True, exist_ok=True)
    status_file = _status_path(database_path, job_id)
    log_file = _log_path(database_path, job_id)
    started_at = datetime.now(UTC).isoformat()
    payload: dict[str, Any] = {
        "job_id": job_id,
        "command": command,
        "status": "starting",
        "pid": None,
        "started_at": started_at,
        "finished_at": None,
        "log": str(log_file),
        "result": None,
    }
    _write(status_file, payload)
    with log_file.open("wb") as handle:
        process = subprocess.Popen(
            [sys.executable, "-c", "from dj_digger.cli import app; app()", *argv],
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env={**os.environ, JOB_ID_ENV: job_id},
            start_new_session=True,
        )
    payload["status"] = "running"
    payload["pid"] = process.pid
    _write(status_file, payload)
    return {"job_id": job_id, "pid": process.pid, "log": str(log_file)}


def record_result(database_path: Path, job_id: str, diagnostic: dict[str, Any]) -> None:
    status_file = _status_path(database_path, job_id)
    try:
        payload = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {"job_id": job_id}
    payload["status"] = diagnostic.get("status", "failed")
    payload["finished_at"] = datetime.now(UTC).isoformat()
    payload["result"] = diagnostic
    _write(status_file, payload)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def list_jobs(database_path: Path) -> list[dict[str, Any]]:
    directory = jobs_dir(database_path)
    if not directory.exists():
        return []
    jobs: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("status") == "running" and not _pid_alive(payload.get("pid", -1)):
            payload["status"] = "unknown"
        jobs.append(payload)
    return jobs
