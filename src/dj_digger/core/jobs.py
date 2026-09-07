"""Durable, presentation-neutral background job facts.

This module deliberately owns no process launching.  The CLI may launch a
process and then use this repository to record its semantic lifecycle.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

JOB_ID_ENV = "DJ_DIGGER_JOB_ID"


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    command: str | None
    status: str
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

    def create(self, command: str | None = None) -> JobRecord:
        job_id = uuid4().hex[:12]
        started_at = datetime.now(UTC).isoformat()
        log_file = jobs_dir(self.database_path) / f"{job_id}.log"
        record = JobRecord(job_id, command, "starting", started_at=started_at, log=str(log_file))
        self._write(record)
        return record

    def start(self, job_id: str, pid: int) -> JobRecord:
        record = self._read(job_id)
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
        self._write(updated)
        return updated

    def record_result(self, job_id: str, diagnostic: dict[str, Any]) -> JobRecord:
        record = self._read(job_id)
        updated = JobRecord(
            record.job_id,
            record.command,
            str(diagnostic.get("status", "failed")),
            record.pid,
            record.started_at,
            datetime.now(UTC).isoformat(),
            record.log,
            dict(diagnostic),
        )
        self._write(updated)
        return updated

    def fail(self, job_id: str, error: str) -> JobRecord:
        return self.record_result(job_id, {"status": "failed", "error": str(error)})

    def list(self) -> list[JobRecord]:
        directory = jobs_dir(self.database_path)
        if not directory.exists():
            return []
        records: list[JobRecord] = []
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                record = _from_dict(payload)
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if record.status == "running" and not _pid_alive(record.pid):
                record = JobRecord(
                    record.job_id,
                    record.command,
                    "unknown",
                    record.pid,
                    record.started_at,
                    record.finished_at,
                    record.log,
                    record.result,
                )
            records.append(record)
        return records

    def _read(self, job_id: str) -> JobRecord:
        path = jobs_dir(self.database_path) / f"{job_id}.json"
        try:
            return _from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"unknown background job: {job_id}") from error

    def _write(self, record: JobRecord) -> None:
        path = jobs_dir(self.database_path) / f"{record.job_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )


def current_job_id() -> str | None:
    return os.environ.get(JOB_ID_ENV)


def _from_dict(payload: dict[str, Any]) -> JobRecord:
    return JobRecord(
        str(payload["job_id"]),
        None if payload.get("command") is None else str(payload["command"]),
        str(payload.get("status", "unknown")),
        None if payload.get("pid") is None else int(payload["pid"]),
        None if payload.get("started_at") is None else str(payload["started_at"]),
        None if payload.get("finished_at") is None else str(payload["finished_at"]),
        None if payload.get("log") is None else str(payload["log"]),
        payload.get("result") if isinstance(payload.get("result"), dict) else None,
    )


def _pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


__all__ = ["JOB_ID_ENV", "JobRecord", "JobRepository", "current_job_id", "jobs_dir"]
