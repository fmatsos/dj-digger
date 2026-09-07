from pathlib import Path

from dj_digger.core.application.jobs import JobRepository


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
    assert failed.result == {"status": "failed", "error": "unavailable"}

    stale = repository.create("stale")
    repository.start(stale.job_id, 2**30)
    assert (
        next(record for record in repository.list() if record.job_id == stale.job_id).status
        == "unknown"
    )
