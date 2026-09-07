import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from dj_digger.core.application.jobs import JobRepository
from dj_digger.core.jobs import JobStateError


def test_job_repository_persists_lifecycle_without_launching_processes(tmp_path: Path) -> None:
    repository = JobRepository(tmp_path / "catalog.sqlite")

    created = repository.create("status")
    started = repository.start(created.job_id, 1234)
    finished = repository.record_result(created.job_id, {"event": "status", "status": "succeeded"})

    assert created.status == "starting"
    assert started.status == "running"
    assert finished.status == "succeeded"
    assert repository.list()[0].result == {"event": "status", "status": "succeeded"}


def test_job_repository_records_sanitized_failure_and_unknown_dead_process(tmp_path: Path) -> None:
    repository = JobRepository(tmp_path / "catalog.sqlite")
    created = repository.create("status")

    failed = repository.fail(created.job_id, "unavailable")
    assert failed.status == "failed"
    assert failed.result == {
        "code": "job_failed",
        "event": "job",
        "status": "failed",
    }

    stale = repository.create("stale")
    repository.start(stale.job_id, 2**30)
    assert (
        next(record for record in repository.list() if record.job_id == stale.job_id).status
        == "unknown"
    )


@pytest.mark.parametrize("method", ("start", "record_result", "fail"))
def test_terminal_jobs_reject_all_further_transitions(tmp_path: Path, method: str) -> None:
    repository = JobRepository(tmp_path / "catalog.sqlite")
    created = repository.create("status")
    repository.record_result(created.job_id, {"status": "succeeded"})

    with pytest.raises(JobStateError):
        if method == "start":
            repository.start(created.job_id, 1234)
        elif method == "record_result":
            repository.record_result(created.job_id, {"status": "failed"})
        else:
            repository.fail(created.job_id, "secret sentinel")


def test_job_result_status_is_allowlisted(tmp_path: Path) -> None:
    repository = JobRepository(tmp_path / "catalog.sqlite")
    created = repository.create("status")

    with pytest.raises(ValueError, match="result status"):
        repository.record_result(created.job_id, {"status": "background"})


def test_concurrent_terminal_writes_are_serialized_and_atomic(tmp_path: Path) -> None:
    repository = JobRepository(tmp_path / "catalog.sqlite")
    created = repository.create("status")

    def finish(index: int) -> str:
        try:
            repository.record_result(created.job_id, {"status": "succeeded", "index": index})
        except JobStateError:
            return "conflict"
        return "committed"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(finish, range(8)))

    assert outcomes.count("committed") == 1
    status_path = tmp_path / "jobs" / f"{created.job_id}.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "succeeded"
    assert not list((tmp_path / "jobs").glob("*.tmp"))


def test_job_persistence_sanitizes_path_and_secret_error_details(tmp_path: Path) -> None:
    repository = JobRepository(tmp_path / "catalog.sqlite")
    created = repository.create("status")
    secret = "local-secret-sentinel /private/library/root/track.flac"

    result = repository.record_result(created.job_id, {"status": "failed", "error": secret})
    serialized = (tmp_path / "jobs" / f"{created.job_id}.json").read_text(encoding="utf-8")

    assert result.result == {"error": "operation failed", "status": "failed"}
    assert secret not in serialized
    assert "/private/library/root" not in serialized
