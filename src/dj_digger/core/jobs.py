"""Durable, presentation-neutral background job facts.

This module deliberately owns no process launching. The CLI may launch a
process and then use this repository to record its semantic lifecycle.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from dj_digger.core.run_log import sanitize_diagnostic

JOB_ID_ENV = "DJ_DIGGER_JOB_ID"
JobStatus = Literal["starting", "running", "succeeded", "partial", "failed", "unknown"]
_TERMINAL_STATUSES: frozenset[JobStatus] = frozenset({"succeeded", "partial", "failed", "unknown"})
_RESULT_STATUSES: frozenset[str] = frozenset({"succeeded", "partial", "failed"})
_THREAD_LOCKS: dict[Path, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class JobStateError(RuntimeError):
    """A durable job transition conflicts with its current state."""


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    command: str | None
    status: JobStatus
    pid: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    log: str | None = None
    result: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "command": self.command,
            "status": self.status,
            "pid": self.pid,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "log": self.log,
            "result": self.result,
        }


def jobs_dir(database_path: Path) -> Path:
    return database_path.parent / "jobs"


class JobRepository:
    """Persist and query durable job state in workspace-owned JSON files."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._directory = jobs_dir(database_path)
        self._lock_path = self._directory / ".lock"

    def create(self, command: str | None = None) -> JobRecord:
        with self._locked():
            self._directory.mkdir(parents=True, exist_ok=True)
            for _ in range(8):
                job_id = uuid4().hex[:12]
                path = self._status_path(job_id)
                if path.exists():
                    continue
                started_at = datetime.now(UTC).isoformat()
                log_file = self._directory / f"{job_id}.log"
                record = JobRecord(
                    job_id,
                    _safe_command(command),
                    "starting",
                    started_at=started_at,
                    log=str(log_file),
                )
                self._write_locked(record)
                return record
        raise RuntimeError("could not allocate a durable background job ID")

    def start(self, job_id: str, pid: int) -> JobRecord:
        if pid <= 0:
            raise ValueError("job process ID must be positive")
        with self._locked():
            record = self._read_locked(job_id)
            if record.status != "starting":
                raise JobStateError(f"cannot start job {job_id}: current status is {record.status}")
            updated = JobRecord(
                record.job_id,
                record.command,
                "running",
                pid,
                record.started_at,
                record.finished_at,
                record.log,
                record.result,
            )
            self._write_locked(updated)
            return updated

    def get(self, job_id: str) -> JobRecord:
        """Read one job under the same lock used for lifecycle transitions."""
        with self._locked():
            return self._read_locked(job_id)

    def record_result(self, job_id: str, diagnostic: dict[str, Any]) -> JobRecord:
        result_status = diagnostic.get("status")
        if not isinstance(result_status, str) or result_status not in _RESULT_STATUSES:
            raise ValueError("job result status must be succeeded, partial, or failed")
        safe_diagnostic = sanitize_diagnostic(diagnostic)
        with self._locked():
            record = self._read_locked(job_id)
            if record.status in _TERMINAL_STATUSES:
                raise JobStateError(
                    f"cannot record result for job {job_id}: current status is {record.status}"
                )
            updated = JobRecord(
                record.job_id,
                record.command,
                result_status,  # type: ignore[arg-type]
                record.pid,
                record.started_at,
                datetime.now(UTC).isoformat(),
                record.log,
                safe_diagnostic,
            )
            self._write_locked(updated)
            return updated

    def fail(self, job_id: str, error: str, *, code: str = "job_failed") -> JobRecord:
        del error
        return self.record_result(
            job_id,
            {"event": "job", "status": "failed", "code": code},
        )

    def list(self) -> list[JobRecord]:
        with self._locked():
            if not self._directory.exists():
                return []
            records: list[JobRecord] = []
            for path in sorted(self._directory.glob("*.json")):
                try:
                    record = _from_dict(json.loads(path.read_text(encoding="utf-8")))
                except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                    continue
                if record.status == "running" and not _pid_alive(record.pid):
                    record = JobRecord(
                        record.job_id,
                        record.command,
                        "unknown",
                        record.pid,
                        record.started_at,
                        datetime.now(UTC).isoformat(),
                        record.log,
                        {"event": "job", "status": "failed", "code": "process_missing"},
                    )
                    self._write_locked(record)
                records.append(record)
            return records

    def _status_path(self, job_id: str) -> Path:
        return self._directory / f"{job_id}.json"

    def _read_locked(self, job_id: str) -> JobRecord:
        path = self._status_path(job_id)
        try:
            return _from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"unknown background job: {job_id}") from error

    def _write_locked(self, record: JobRecord) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._status_path(record.job_id)
        payload = json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{record.job_id}.", suffix=".tmp", dir=self._directory
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            _fsync_directory(self._directory)
        finally:
            temporary_path.unlink(missing_ok=True)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        lock = _thread_lock(self._lock_path)
        with lock:
            self._directory.mkdir(parents=True, exist_ok=True)
            with self._lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def current_job_id() -> str | None:
    return os.environ.get(JOB_ID_ENV)


def record_result(database_path: Path, job_id: str, diagnostic: dict[str, Any]) -> None:
    JobRepository(database_path).record_result(job_id, diagnostic)


def list_jobs(database_path: Path) -> list[dict[str, Any]]:
    return [record.as_dict() for record in JobRepository(database_path).list()]


def _from_dict(payload: dict[str, Any]) -> JobRecord:
    status = payload.get("status", "unknown")
    if status not in {"starting", "running", "succeeded", "partial", "failed", "unknown"}:
        raise ValueError("invalid durable job status")
    return JobRecord(
        str(payload["job_id"]),
        None if payload.get("command") is None else _safe_command(str(payload["command"])),
        status,
        None if payload.get("pid") is None else int(payload["pid"]),
        None if payload.get("started_at") is None else str(payload["started_at"]),
        None if payload.get("finished_at") is None else str(payload["finished_at"]),
        None if payload.get("log") is None else str(payload["log"]),
        sanitize_diagnostic(payload["result"]) if isinstance(payload.get("result"), dict) else None,
    )


def _safe_command(command: str | None) -> str | None:
    if command is None:
        return None
    return command if command.isidentifier() and len(command) <= 64 else "unknown"


def _pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _thread_lock(path: Path) -> threading.RLock:
    key = path.resolve()
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _THREAD_LOCKS[key] = lock
        return lock


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "JOB_ID_ENV",
    "JobRecord",
    "JobRepository",
    "JobStateError",
    "JobStatus",
    "current_job_id",
    "jobs_dir",
    "list_jobs",
    "record_result",
]
