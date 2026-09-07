"""CLI background launcher and durable-job command adapter."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from dj_digger.core.jobs import JOB_ID_ENV, JobRepository


def launch(database_path: Path, command: str, argv: list[str]) -> dict[str, Any]:
    """Launch one detached CLI command and persist its lifecycle facts."""
    repository = JobRepository(database_path)
    created = repository.create(command)
    log_file = Path(created.log or (database_path.parent / "jobs" / f"{created.job_id}.log"))
    with log_file.open("wb") as handle:
        process = subprocess.Popen(
            [sys.executable, "-c", "from dj_digger.cli import app; app()", *argv],
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env={**os.environ, JOB_ID_ENV: created.job_id},
            start_new_session=True,
        )
    repository.start(created.job_id, process.pid)
    return {"job_id": created.job_id, "pid": process.pid, "log": str(log_file)}


def jobs_payload(database_path: Path) -> dict[str, Any]:
    return {
        "event": "jobs",
        "status": "succeeded",
        "jobs": [record.as_dict() for record in JobRepository(database_path).list()],
    }


__all__ = ["jobs_payload", "launch"]
