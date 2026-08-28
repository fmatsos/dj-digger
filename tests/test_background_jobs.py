import json
import sys
import time
from pathlib import Path

import pytest

from dj_digger import background

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
