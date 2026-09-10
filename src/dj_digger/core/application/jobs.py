"""Typed application access to durable job facts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dj_digger.core.errors import UNCLASSIFIED
from dj_digger.core.jobs import (
    JOB_ID_ENV,
    JobRecord,
    JobRepository,
    JobStateError,
    JobStatus,
    current_job_id,
    jobs_dir,
    list_jobs,
    record_result,
)


class JobsUseCase:
    """Expose the durable lifecycle without owning process execution."""

    def __init__(self, repository: JobRepository) -> None:
        self._repository = repository

    def create(self, command: str | None = None) -> JobRecord:
        return self._repository.create(command)

    def start(self, job_id: str, pid: int) -> JobRecord:
        return self._repository.start(job_id, pid)

    def get(self, job_id: str) -> JobRecord:
        return self._repository.get(job_id)

    def record_result(self, job_id: str, diagnostic: Mapping[str, Any]) -> JobRecord:
        return self._repository.record_result(job_id, diagnostic)

    def fail(self, job_id: str, error: str, *, error_class: str = UNCLASSIFIED) -> JobRecord:
        return self._repository.fail(job_id, error, error_class=error_class)

    def mark_unknown(self, job_id: str, *, code: str = "cleanup_failed") -> JobRecord:
        return self._repository.mark_unknown(job_id, code=code)

    def list(self) -> list[JobRecord]:
        return self._repository.list()


__all__ = [
    "JOB_ID_ENV",
    "JobRecord",
    "JobRepository",
    "JobStateError",
    "JobStatus",
    "JobsUseCase",
    "current_job_id",
    "jobs_dir",
    "list_jobs",
    "record_result",
]
