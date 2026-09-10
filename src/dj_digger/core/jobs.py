"""Durable, presentation-neutral background job facts.

This module deliberately owns no process launching. The CLI may launch a
process and then use this repository to record its semantic lifecycle.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from dj_digger.core.errors import UNCLASSIFIED, StateConflictError
from dj_digger.core.run_log import sanitize_diagnostic

JOB_ID_ENV = "DJ_DIGGER_JOB_ID"


class JobStatus(StrEnum):
    """Lifecycle of one detached background command."""

    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    UNKNOWN = "unknown"


TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.PARTIAL, JobStatus.FAILED, JobStatus.UNKNOWN}
)
_RESULT_STATUSES: frozenset[str] = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.PARTIAL, JobStatus.FAILED}
)
_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "cleanup_failed",
        "job_failed",
        "launch_failed",
        "launch_start_failed",
        "process_missing",
    }
)
_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_THREAD_LOCKS: dict[Path, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class JobStateError(StateConflictError):
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
                    JobStatus.STARTING,
                    started_at=started_at,
                    log=str(log_file),
                )
                self._write_locked(record)
                return record
        raise RuntimeError("could not allocate a durable background job ID")

    def start(self, job_id: str, pid: int) -> JobRecord:
        _validate_job_id(job_id)
        if pid <= 0:
            raise ValueError("job process ID must be positive")
        with self._locked():
            record = self._read_locked(job_id)
            if record.status != JobStatus.STARTING:
                raise JobStateError(f"cannot start job {job_id}: current status is {record.status}")
            updated = JobRecord(
                record.job_id,
                record.command,
                JobStatus.RUNNING,
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
        _validate_job_id(job_id)
        with self._locked():
            return self._read_locked(job_id)

    def record_result(self, job_id: str, diagnostic: Mapping[str, Any]) -> JobRecord:
        _validate_job_id(job_id)
        raw_status = diagnostic.get("status")
        if not isinstance(raw_status, str) or raw_status not in _RESULT_STATUSES:
            raise ValueError("job result status must be succeeded, partial, or failed")
        result_status = JobStatus(raw_status)
        safe_diagnostic = sanitize_diagnostic(diagnostic)
        with self._locked():
            record = self._read_locked(job_id)
            if record.status in TERMINAL_JOB_STATUSES:
                raise JobStateError(
                    f"cannot record result for job {job_id}: current status is {record.status}"
                )
            updated = JobRecord(
                record.job_id,
                record.command,
                result_status,
                record.pid,
                record.started_at,
                datetime.now(UTC).isoformat(),
                record.log,
                safe_diagnostic,
            )
            self._write_locked(updated)
            return updated

    def fail(
        self,
        job_id: str,
        error: str,
        *,
        code: str = "job_failed",
        error_class: str = UNCLASSIFIED,
    ) -> JobRecord:
        """Record a job failure with an explicitly declared failure class.

        ``error`` carries private detail and is never persisted; ``error_class``
        is what a caller holding the real exception derived with ``classify``.
        """
        safe_code = code if code in _FAILURE_CODES else "job_failed"
        return self.record_result(
            job_id,
            {
                "event": "job",
                "status": JobStatus.FAILED,
                "code": safe_code,
                "error": error,
                "error_class": error_class,
            },
        )

    def mark_unknown(self, job_id: str, *, code: str = "cleanup_failed") -> JobRecord:
        """Record that a process outcome cannot be trusted after cleanup failure."""
        _validate_job_id(job_id)
        safe_code = code if code in _FAILURE_CODES else "job_failed"
        with self._locked():
            record = self._read_locked(job_id)
            if record.status in TERMINAL_JOB_STATUSES:
                raise JobStateError(
                    f"cannot mark job {job_id} unknown: current status is {record.status}"
                )
            updated = JobRecord(
                record.job_id,
                record.command,
                JobStatus.UNKNOWN,
                record.pid,
                record.started_at,
                datetime.now(UTC).isoformat(),
                record.log,
                {
                    "event": "job",
                    "status": JobStatus.UNKNOWN,
                    "code": safe_code,
                    "error": "operation outcome is unknown",
                },
            )
            self._write_locked(updated)
            return updated

    def list(self) -> list[JobRecord]:
        if not self._directory.is_dir():
            return []
        with self._locked():
            records: list[JobRecord] = []
            for path in sorted(self._directory.glob("*.json")):
                try:
                    record = _from_dict(json.loads(path.read_text(encoding="utf-8")))
                except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                    continue
                if record.status == JobStatus.RUNNING and not _pid_alive(record.pid):
                    record = JobRecord(
                        record.job_id,
                        record.command,
                        JobStatus.UNKNOWN,
                        record.pid,
                        record.started_at,
                        datetime.now(UTC).isoformat(),
                        record.log,
                        {
                            "event": "job",
                            "status": JobStatus.FAILED,
                            "code": "process_missing",
                        },
                    )
                    self._write_locked(record)
                records.append(record)
            return records

    def _status_path(self, job_id: str) -> Path:
        _validate_job_id(job_id)
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
    job_id = os.environ.get(JOB_ID_ENV)
    return job_id if job_id is not None and _is_valid_job_id(job_id) else None


def record_result(database_path: Path, job_id: str, diagnostic: Mapping[str, Any]) -> None:
    JobRepository(database_path).record_result(job_id, diagnostic)


def list_jobs(database_path: Path) -> list[dict[str, Any]]:
    return [record.as_dict() for record in JobRepository(database_path).list()]


def _from_dict(payload: object) -> JobRecord:
    """Decode one durable record, rejecting non-object JSON consistently."""
    if not isinstance(payload, Mapping):
        raise ValueError("durable job record must be a JSON object")
    raw_status = payload.get("status", JobStatus.UNKNOWN)
    try:
        status = JobStatus(raw_status)
    except ValueError:
        raise ValueError("invalid durable job status") from None
    job_id = str(payload["job_id"])
    _validate_job_id(job_id)
    return JobRecord(
        job_id,
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


def _is_valid_job_id(job_id: str) -> bool:
    return _JOB_ID.fullmatch(job_id) is not None


def _validate_job_id(job_id: str) -> None:
    if not _is_valid_job_id(job_id):
        raise ValueError("invalid background job ID")


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
    "TERMINAL_JOB_STATUSES",
    "JobRecord",
    "JobRepository",
    "JobStateError",
    "JobStatus",
    "current_job_id",
    "jobs_dir",
    "list_jobs",
    "record_result",
]
