"""Compatibility facade for durable jobs and the CLI launcher."""

from pathlib import Path
from typing import Any

from dj_digger.cli.commands.jobs import launch
from dj_digger.core.application.jobs import (
    JOB_ID_ENV,
    JobRecord,
    JobRepository,
    current_job_id,
    jobs_dir,
)


def record_result(database_path: Path, job_id: str, diagnostic: dict[str, Any]) -> None:
    JobRepository(database_path).record_result(job_id, diagnostic)


def list_jobs(database_path: Path) -> list[dict[str, Any]]:
    return [record.as_dict() for record in JobRepository(database_path).list()]


__all__ = [
    "JOB_ID_ENV",
    "JobRecord",
    "JobRepository",
    "current_job_id",
    "jobs_dir",
    "launch",
    "list_jobs",
    "record_result",
]
