"""Presentation mapping for durable background jobs."""

from collections.abc import Sequence
from typing import Any

from dj_digger.core.diagnostics import JobsDiagnostic
from dj_digger.core.jobs import JobRecord


def jobs_payload(records: Sequence[JobRecord | dict[str, Any]]) -> JobsDiagnostic:
    return {
        "event": "jobs",
        "status": "succeeded",
        "jobs": [
            record.as_dict() if isinstance(record, JobRecord) else dict(record)
            for record in records
        ],
    }


__all__ = ["jobs_payload"]
