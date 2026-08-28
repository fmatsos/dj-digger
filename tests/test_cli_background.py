import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dj_digger import cli
from dj_digger.cli import app


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


@pytest.fixture
def config(tmp_path: Path) -> Path:
    source = tmp_path / "music"
    source.mkdir()
    return write_config(tmp_path, source=source, exports=tmp_path / "exports")


def _fake_launch(calls: list) -> callable:
    def launch(database: Path, command: str, argv: list) -> dict:
        calls.append({"database": database, "command": command, "argv": argv})
        log = database.parent / "jobs" / "abc123.log"
        return {"job_id": "abc123", "pid": 4242, "log": str(log)}

    return launch


def test_analyze_background_launches_a_detached_job_without_running_analysis(
    tmp_path: Path, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list = []
    monkeypatch.setattr(cli.background, "launch", _fake_launch(calls))

    result = CliRunner().invoke(app, ["analyze", "--config", str(config), "--background", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {
        "event": "analyze",
        "status": "background",
        "job_id": "abc123",
        "pid": 4242,
        "log": str(tmp_path / "jobs" / "abc123.log"),
    }
    assert len(calls) == 1
    assert calls[0]["command"] == "analyze"
    assert "--background" not in calls[0]["argv"]
    assert "--json" in calls[0]["argv"]
    assert calls[0]["argv"][0] == "analyze"


def test_refresh_background_launches_a_detached_job(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list = []
    monkeypatch.setattr(cli.background, "launch", _fake_launch(calls))

    result = CliRunner().invoke(
        app, ["refresh", "--config", str(config), "--workers", "3", "--background"]
    )

    assert result.exit_code == 0
    assert calls[0]["command"] == "refresh"
    assert "--workers" in calls[0]["argv"] and "3" in calls[0]["argv"]
    assert "--background" not in calls[0]["argv"]


def test_duplicates_background_requires_analyze(config: Path) -> None:
    result = CliRunner().invoke(
        app, ["duplicates", "--config", str(config), "--list", "--background"]
    )

    assert result.exit_code != 0
    assert "--background is only valid with --analyze" in result.output


def test_duplicates_analyze_background_launches_a_detached_job(
    config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list = []
    monkeypatch.setattr(cli.background, "launch", _fake_launch(calls))

    result = CliRunner().invoke(
        app, ["duplicates", "--config", str(config), "--analyze", "--background"]
    )

    assert result.exit_code == 0
    assert calls[0]["command"] == "duplicates"
    assert "--analyze" in calls[0]["argv"]
    assert "--background" not in calls[0]["argv"]


def test_jobs_command_reports_launched_jobs(config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_jobs = [{"job_id": "abc123", "status": "succeeded"}]
    monkeypatch.setattr(cli.background, "list_jobs", lambda database: fake_jobs)

    result = CliRunner().invoke(app, ["jobs", "--config", str(config), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {"event": "jobs", "status": "succeeded", "jobs": fake_jobs}
