"""CLI background launcher and durable-job command adapter."""

from __future__ import annotations

import os
import signal
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
    process: Any = None
    try:
        with log_file.open("wb") as handle:
            process = subprocess.Popen(
                [sys.executable, "-c", "from dj_digger.cli import app; app()", *argv],
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env={**os.environ, JOB_ID_ENV: created.job_id},
                start_new_session=True,
            )
            try:
                repository.start(created.job_id, process.pid)
            except Exception:
                current = repository.get(created.job_id)
                if current.status in {"succeeded", "partial", "failed", "unknown"}:
                    return {"job_id": created.job_id, "pid": process.pid, "log": str(log_file)}
                _terminate_bounded(process)
                raise
    except BaseException:
        code = "launch_start_failed" if process is not None else "launch_failed"
        _record_failure(repository, created.job_id, code)
        raise RuntimeError(f"background launch failed: {code}") from None
    return {"job_id": created.job_id, "pid": process.pid, "log": str(log_file)}


def _record_failure(repository: JobRepository, job_id: str, code: str) -> None:
    try:
        repository.fail(job_id, "", code=code)
    except Exception:
        # A child may have committed its terminal result before the parent
        # observed the failed start. Never overwrite that result.
        pass


def _terminate_bounded(process: Any) -> None:
    """Terminate and reap a detached process without leaving an orphan."""
    try:
        if process.poll() is not None:
            return
    except AttributeError:
        pass
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (AttributeError, OSError):
        try:
            process.terminate()
        except (AttributeError, OSError):
            return
    try:
        process.wait(timeout=1.0)
        return
    except (subprocess.TimeoutExpired, AttributeError, OSError):
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (AttributeError, OSError):
        try:
            process.kill()
        except (AttributeError, OSError):
            return
    try:
        process.wait(timeout=1.0)
    except (subprocess.TimeoutExpired, AttributeError, OSError):
        pass


def jobs_payload(database_path: Path) -> dict[str, Any]:
    return {
        "event": "jobs",
        "status": "succeeded",
        "jobs": [record.as_dict() for record in JobRepository(database_path).list()],
    }


__all__ = ["jobs_payload", "launch"]
