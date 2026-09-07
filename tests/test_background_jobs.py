import json
import sys
import time
from pathlib import Path

import pytest

from dj_digger import background
from dj_digger.core.jobs import JobRepository, JobStateError

_VENV_PYTHON = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"


def write_config(path: Path, *, source: Path, exports: Path) -> Path:
    config = path / "dj-digger.toml"
    config.write_text(
        "\n".join(
            [
                "[workspace]",
                'database = "catalog.sqlite"',
                f'exports = "{exports}"',
                "",
                "[[library.sources]]",
                'id = "required"',
                f'path = "{source}"',
                "set_eligible = true",
                "analyze = false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def _wait_for_completion(database: Path, job_id: str, *, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    status_file = background.jobs_dir(database) / f"{job_id}.json"
    while time.monotonic() < deadline:
        if status_file.exists():
            payload = json.loads(status_file.read_text(encoding="utf-8"))
            if payload.get("status") not in ("starting", "running"):
                return payload
        time.sleep(0.1)
    raise AssertionError("background job did not finish in time")


@pytest.mark.skipif(
    not _VENV_PYTHON.exists(), reason="requires the project .venv with dj_digger installed"
)
def test_launch_runs_a_detached_command_and_records_its_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "executable", str(_VENV_PYTHON))
    source = tmp_path / "music"
    source.mkdir()
    config = write_config(tmp_path, source=source, exports=tmp_path / "exports")
    database = tmp_path / "catalog.sqlite"

    info = background.launch(database, "status", ["status", "--config", str(config)])

    assert info["pid"] > 0
    payload = _wait_for_completion(database, info["job_id"])
    assert payload["status"] == "succeeded"
    assert payload["result"]["event"] == "status"
    assert Path(payload["log"]).exists()

    jobs = background.list_jobs(database)
    assert [job["job_id"] for job in jobs] == [info["job_id"]]
    assert jobs[0]["status"] == "succeeded"


def test_list_jobs_flags_a_dead_process_that_never_reported(tmp_path: Path) -> None:
    database = tmp_path / "catalog.sqlite"
    status_file = background.jobs_dir(database) / "stale.json"
    status_file.parent.mkdir(parents=True)
    status_file.write_text(
        json.dumps({"job_id": "stale", "status": "running", "pid": 2**30}),
        encoding="utf-8",
    )

    jobs = background.list_jobs(database)

    assert jobs[0]["status"] == "unknown"


def test_list_jobs_returns_empty_when_no_jobs_ran(tmp_path: Path) -> None:
    assert background.list_jobs(tmp_path / "catalog.sqlite") == []


def test_launcher_failure_records_safe_terminal_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_open = Path.open

    def fail_open(path: Path, *args, **kwargs):
        if path.suffix == ".log":
            raise OSError("/private/library/root/local-secret")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_open)

    with pytest.raises(RuntimeError, match="launch_failed"):
        background.launch(tmp_path / "catalog.sqlite", "status", ["status"])

    jobs = JobRepository(tmp_path / "catalog.sqlite").list()
    assert jobs[0].status == "failed"
    serialized = (tmp_path / "jobs" / f"{jobs[0].job_id}.json").read_text(encoding="utf-8")
    assert "local-secret" not in serialized
    assert "/private/library/root" not in serialized


def test_launcher_spawn_failure_records_safe_terminal_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dj_digger.cli.commands.jobs.subprocess.Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("/private/library/root/local-secret")
        ),
    )

    with pytest.raises(RuntimeError, match="launch_failed"):
        background.launch(tmp_path / "catalog.sqlite", "status", ["status"])

    jobs = JobRepository(tmp_path / "catalog.sqlite").list()
    assert jobs[0].status == "failed"


def test_launcher_start_failure_reaps_child_and_records_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    class Child:
        pid = 4242

        def terminate(self) -> None:
            events.append("terminate")

        def wait(self, timeout: float) -> None:
            events.append(f"wait:{timeout}")

    monkeypatch.setattr(
        "dj_digger.cli.commands.jobs.subprocess.Popen", lambda *_args, **_kwargs: Child()
    )
    monkeypatch.setattr(
        JobRepository,
        "start",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(JobStateError("race")),
    )
    monkeypatch.setattr(
        "dj_digger.cli.commands.jobs.os.killpg",
        lambda *_args: (_ for _ in ()).throw(OSError()),
    )

    with pytest.raises(RuntimeError, match="launch_start_failed"):
        background.launch(tmp_path / "catalog.sqlite", "status", ["status"])

    assert events == ["terminate", "wait:1.0"]


def test_launcher_does_not_overwrite_child_result_when_start_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Child:
        pid = 4242

        def poll(self) -> int:
            return 0

    original_start = JobRepository.start

    def race_start(repository: JobRepository, job_id: str, pid: int):
        repository.record_result(job_id, {"status": "succeeded", "event": "status"})
        return original_start(repository, job_id, pid)

    monkeypatch.setattr(
        "dj_digger.cli.commands.jobs.subprocess.Popen", lambda *_args, **_kwargs: Child()
    )
    monkeypatch.setattr(JobRepository, "start", race_start)

    info = background.launch(tmp_path / "catalog.sqlite", "status", ["status"])

    assert info["pid"] == 4242
    job = JobRepository(tmp_path / "catalog.sqlite").list()[0]
    assert job.status == "succeeded"
