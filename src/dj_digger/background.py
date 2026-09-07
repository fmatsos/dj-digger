"""Compatibility facade for durable jobs and the CLI launcher."""

from dj_digger.cli.commands.jobs import launch
from dj_digger.core.application.jobs import (
    JOB_ID_ENV,
    JobRecord,
    JobRepository,
    current_job_id,
    jobs_dir,
    list_jobs,
    record_result,
)

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
