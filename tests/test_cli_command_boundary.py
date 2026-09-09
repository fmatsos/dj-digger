"""Every command shares one execution boundary: logging, exits, job results."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dj_digger.cli import app, runtime
from dj_digger.core.jobs import JOB_ID_ENV, JobRepository


def _write_config(path: Path) -> Path:
    source = path / "library"
    source.mkdir(parents=True, exist_ok=True)
    config = path / "config.toml"
    config.write_text(
        "\n".join(
            [
                "[workspace]",
                'database = "catalog.sqlite"',
                'exports = "exports"',
                "",
                "[[library.sources]]",
                'id = "library"',
                f'path = "{source}"',
                "set_eligible = true",
                "analyze = false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config


@pytest.mark.parametrize("command", ["scan", "metadata", "status"])
def test_every_command_writes_the_workspace_run_log(tmp_path: Path, command: str) -> None:
    config = _write_config(tmp_path)

    result = CliRunner().invoke(app, [command, "--config", str(config), "--json"])

    assert result.exit_code in {0, 2}
    log = tmp_path / "logs" / "dj-digger.log"
    assert log.is_file()
    assert f" {command} " in log.read_text(encoding="utf-8")


@pytest.mark.parametrize("command", ["scan", "metadata"])
def test_background_results_are_recorded_for_every_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    """scan and metadata used to bypass background result recording."""
    config = _write_config(tmp_path)
    repository = JobRepository(tmp_path / "catalog.sqlite")
    job = repository.create(command)
    repository.start(job.job_id, 1)
    monkeypatch.setenv(JOB_ID_ENV, job.job_id)

    result = CliRunner().invoke(app, [command, "--config", str(config), "--json"])

    assert result.exit_code in {0, 2}
    assert repository.get(job.job_id).result is not None


@pytest.mark.parametrize("command", ["scan", "metadata", "status", "doctor", "export"])
def test_a_broken_config_fails_identically_for_every_command(tmp_path: Path, command: str) -> None:
    broken = tmp_path / "config.toml"
    broken.write_text("[workspace]\n", encoding="utf-8")

    result = CliRunner().invoke(app, [command, "--config", str(broken), "--json"])

    assert result.exit_code == runtime.EXIT_FAILED
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == "failed"
    assert payload["code"] == "invalid_config"
    assert payload["event"] == command


def test_partial_results_map_to_exit_code_two_for_scan_and_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """scan used to have no partial handling at all."""
    config = _write_config(tmp_path)
    monkeypatch.setattr(
        "dj_digger.core.application.app.CoreApplication.metadata",
        lambda self, request=None: type(
            "Result", (), {"status": "partial", "extracted": 1, "failed": 1, "skipped": 0}
        )(),
    )

    result = CliRunner().invoke(app, ["metadata", "--config", str(config), "--json"])

    assert result.exit_code == runtime.EXIT_PARTIAL


def test_unexpected_failures_are_logged_with_their_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An unexpected exception must leave evidence beyond a sanitized status."""
    config = _write_config(tmp_path)
    monkeypatch.setattr(
        "dj_digger.core.application.app.CoreApplication.status",
        lambda self: (_ for _ in ()).throw(KeyError("internal-bug")),
    )

    with caplog.at_level("ERROR", logger="dj_digger"):
        result = CliRunner().invoke(app, ["status", "--config", str(config), "--json"])

    assert result.exit_code == runtime.EXIT_FAILED
    record = next(entry for entry in caplog.records if entry.name == "dj_digger")
    assert record.exc_info is not None
    assert "internal-bug" in caplog.text


@pytest.mark.parametrize(
    ("verbosity", "expected"), [(0, "WARNING"), (1, "INFO"), (2, "DEBUG"), (3, "DEBUG")]
)
def test_verbosity_drives_the_logging_level(verbosity: int, expected: str) -> None:
    import logging

    runtime.configure_logging(verbosity)

    assert logging.getLevelName(logging.getLogger("dj_digger").level) == expected
