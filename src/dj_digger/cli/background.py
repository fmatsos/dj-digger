"""CLI-owned detached process launcher and durable-job adapter."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from dj_digger.core.jobs import (
    JOB_ID_ENV,
    JobRecord,
    JobRepository,
    current_job_id,
    jobs_dir,
    list_jobs,
    record_result,
)


class JobCleanupError(RuntimeError):
    """The launcher could not prove a failed child was reaped."""


def launch(database_path: Path, command: str, argv: list[str]) -> dict[str, Any]:
    """Launch one detached public CLI command and persist its lifecycle facts."""

    repository = JobRepository(database_path)
    created = repository.create(command)
    log_file = Path(created.log or (database_path.parent / "jobs" / f"{created.job_id}.log"))
    process: Any = None
    try:
        with log_file.open("wb") as handle:
            process = subprocess.Popen(
                [sys.executable, "-m", "dj_digger.cli", *argv],
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
                raise
    except BaseException:
        code = "launch_start_failed" if process is not None else "launch_failed"
        cleanup_error: JobCleanupError | None = None
        if process is not None:
            try:
                _terminate_bounded(process)
            except JobCleanupError as error:
                cleanup_error = error
        persistence_failed = False
        try:
            if cleanup_error is not None:
                repository.mark_unknown(created.job_id, code="cleanup_failed")
            else:
                repository.fail(created.job_id, "", code=code)
        except Exception:
            persistence_failed = True
        if cleanup_error is not None and persistence_failed:
            raise RuntimeError(
                "background launch failed: cleanup and failure persistence failed"
            ) from None
        if cleanup_error is not None:
            raise RuntimeError("background launch failed: cleanup could not be verified") from None
        if persistence_failed:
            raise RuntimeError("background launch failed: failure persistence failed") from None
        raise RuntimeError(f"background launch failed: {code}") from None
    return {"job_id": created.job_id, "pid": process.pid, "log": str(log_file)}


def _terminate_bounded(process: Any) -> None:
    """Terminate and reap a detached process without leaving an orphan."""

    if _reaped(process):
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (AttributeError, OSError):
        try:
            process.terminate()
        except (AttributeError, OSError) as error:
            raise JobCleanupError("unable to terminate background process") from error
    try:
        process.wait(timeout=1.0)
    except (subprocess.TimeoutExpired, AttributeError, OSError):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (AttributeError, OSError):
            try:
                process.kill()
            except (AttributeError, OSError) as error:
                raise JobCleanupError("unable to kill background process") from error
        try:
            process.wait(timeout=1.0)
        except (subprocess.TimeoutExpired, AttributeError, OSError) as error:
            raise JobCleanupError("background process did not exit after kill") from error
    if not _reaped(process):
        raise JobCleanupError("background process reap could not be verified")


def _reaped(process: Any) -> bool:
    try:
        return process.poll() is not None
    except (AttributeError, OSError):
        try:
            return process.returncode is not None
        except AttributeError:
            return False


__all__ = [
    "JOB_ID_ENV",
    "JobCleanupError",
    "JobRecord",
    "JobRepository",
    "current_job_id",
    "jobs_dir",
    "launch",
    "list_jobs",
    "record_result",
    "os",
    "signal",
    "subprocess",
]
