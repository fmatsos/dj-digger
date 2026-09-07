"""Compatibility exports for the CLI background adapter."""

from dj_digger.cli.background import (  # noqa: F401  # noqa: F401
    JOB_ID_ENV,
    JobCleanupError,
    JobRecord,
    JobRepository,
    _reaped,
    _terminate_bounded,
    current_job_id,
    jobs_dir,
    launch,
    list_jobs,
    os,
    record_result,
    signal,
    subprocess,
)
from dj_digger.cli.presenters.jobs import jobs_payload

__all__ = [
    "JOB_ID_ENV",
    "JobCleanupError",
    "JobRecord",
    "JobRepository",
    "current_job_id",
    "jobs_dir",
    "jobs_payload",
    "launch",
    "list_jobs",
    "record_result",
]
