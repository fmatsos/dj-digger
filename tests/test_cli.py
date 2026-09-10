import json
from importlib import import_module
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from dj_digger.cli import app, runtime
from dj_digger.cli.presenters.metadata import metadata_payload
from dj_digger.cli.presenters.scan import scan_payload
from dj_digger.core.application import MetadataRunResult, ScanRunResult, ScanSourceResult
from dj_digger.core.errors import InvalidInputError


def _write_config(path: Path, filename: str = "config.toml", *, source_id: str = "library") -> Path:
    source = path / "library"
    source.mkdir(parents=True, exist_ok=True)
    config = path / filename
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "\n".join(
            [
                "[workspace]",
                'database = "catalog.sqlite"',
                'exports = "exports"',
                "",
                "[[library.sources]]",
                f'id = "{source_id}"',
                f'path = "{source}"',
                "set_eligible = true",
                "analyze = false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def test_help_exits_successfully_and_describes_the_application() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0


def test_no_command_displays_help_and_available_commands() -> None:
    result = CliRunner().invoke(app)

    assert result.exit_code == 0


def test_scan_presenter_preserves_compact_success_and_failure_keys() -> None:
    success = scan_payload(ScanRunResult((ScanSourceResult("source", True, 4),)))
    failure = scan_payload(ScanRunResult((ScanSourceResult("source", False, 5, "unavailable"),)))

    assert success == {
        "event": "scan",
        "status": "succeeded",
        "scans": [{"source_id": "source", "succeeded": True, "run_id": 4, "error": None}],
    }
    assert failure["status"] == "failed"
    assert failure["scans"][0]["error"] == "unavailable"


def test_metadata_presenter_preserves_compact_result_keys() -> None:
    assert metadata_payload(MetadataRunResult(2, 1, 3)) == {
        "event": "metadata",
        "status": "partial",
        "extracted": 2,
        "failed": 1,
        "skipped": 3,
    }


def test_metadata_command_uses_failure_exit_code(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("", encoding="utf-8")
    cli_module = import_module("dj_digger.cli.app")
    monkeypatch.setattr(
        cli_module,
        "execute_metadata",
        lambda _config, _source, _path, _force: {
            "event": "metadata",
            "status": "failed",
            "error": "dependency unavailable",
        },
    )

    result = CliRunner().invoke(app, ["metadata", "--config", str(config), "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "failed"


def test_scan_command_uses_failure_exit_code(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("", encoding="utf-8")
    cli_module = import_module("dj_digger.cli.app")
    monkeypatch.setattr(
        cli_module,
        "execute_scan",
        lambda _config, _source: {"event": "scan", "status": "failed", "scans": []},
    )

    result = CliRunner().invoke(app, ["scan", "--config", str(config), "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "failed"


@pytest.mark.parametrize("command", ["scan", "metadata", "refresh"])
def test_malformed_config_returns_typed_json_failure(tmp_path: Path, command: str) -> None:
    config = tmp_path / "malformed.toml"
    config.write_text("[workspace\n", encoding="utf-8")

    result = CliRunner().invoke(app, [command, "--config", str(config), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["event"] == command
    assert payload["status"] == "failed"
    assert payload["code"] == "invalid_config"
    assert "invalid configuration" in payload["error"]


@pytest.mark.parametrize("relative_path", ["config.toml", "config/config.toml"])
def test_status_discovers_config_in_current_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative_path: str
) -> None:
    _write_config(tmp_path, relative_path)
    empty_home = tmp_path / "home"
    empty_home.mkdir()
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["status", "--json"], env={"HOME": str(empty_home)})

    assert result.exit_code == 0
    assert json.loads(result.stdout)["event"] == "status"


def test_status_falls_back_to_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    _write_config(home / ".dj-digger")
    monkeypatch.chdir(workspace)

    result = CliRunner().invoke(app, ["status", "--json"], env={"HOME": str(home)})

    assert result.exit_code == 0
    assert json.loads(result.stdout)["event"] == "status"


def test_workspace_config_takes_precedence_over_user_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_config(workspace, source_id="workspace")
    home = tmp_path / "home"
    _write_config(home / ".dj-digger", source_id="global")
    monkeypatch.chdir(workspace)

    result = CliRunner().invoke(app, ["status", "--json"], env={"HOME": str(home)})

    assert json.loads(result.output)["sources"][0]["source_id"] == "workspace"


def test_explicit_config_takes_precedence_over_discovered_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_config(workspace, source_id="workspace")
    explicit = _write_config(tmp_path / "explicit", source_id="explicit")
    monkeypatch.chdir(workspace)

    result = CliRunner().invoke(
        app, ["status", "--config", str(explicit), "--json"], env={"HOME": str(tmp_path)}
    )

    assert json.loads(result.output)["sources"][0]["source_id"] == "explicit"


def test_missing_discovered_config_requests_explicit_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(workspace)

    result = CliRunner().invoke(app, ["status"], env={"HOME": str(home)})

    assert result.exit_code == 2


def test_run_closes_its_application_when_the_action_fails(monkeypatch) -> None:
    """A failing action must still close the catalog session it was given."""
    events: list[str] = []

    class FakeApplication:
        def __init__(self, _config) -> None:
            events.append("created")

        def __enter__(self):
            events.append("entered")
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            assert exc_type is RuntimeError
            events.append("closed")

    class FakeLogger:
        def __init__(self, _database) -> None:
            pass

        def write(self, _diagnostic) -> None:
            pass

    config = type("Config", (), {"database": Path("catalog.sqlite")})()
    monkeypatch.setattr(runtime.WorkspaceConfig, "load", staticmethod(lambda _path: config))

    with pytest.raises(typer.Exit):
        runtime.run_command(
            Path("config.toml"),
            lambda _service: (_ for _ in ()).throw(RuntimeError("boom")),
            event="probe",
            application_factory=FakeApplication,
            logger_factory=FakeLogger,
        )

    assert events == ["created", "entered", "closed"]


def test_run_records_the_failure_class_derived_from_the_exception_type(monkeypatch) -> None:
    """The persisted diagnostic carries a typed failure class, not a guess."""
    written: list[dict[str, object]] = []

    class FakeApplication:
        def __init__(self, _config) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    class FakeLogger:
        def __init__(self, _database) -> None:
            pass

        def write(self, diagnostic) -> None:
            written.append(diagnostic)

    def failing(_service):
        raise InvalidInputError("limit must be positive")

    config = type("Config", (), {"database": Path("catalog.sqlite")})()
    monkeypatch.setattr(runtime.WorkspaceConfig, "load", staticmethod(lambda _path: config))

    diagnostic = runtime.execute_command(
        Path("config.toml"),
        failing,
        event="probe",
        application_factory=FakeApplication,
        logger_factory=FakeLogger,
    )

    assert diagnostic["status"] == "failed"
    assert diagnostic["error_class"] == "invalid input"
    assert written == [diagnostic]


@pytest.mark.parametrize(
    ("status", "expected"),
    [("succeeded", 0), ("partial", 2), ("failed", 1), (None, 0)],
)
def test_every_command_shares_one_status_to_exit_code_mapping(
    status: str | None, expected: int
) -> None:
    assert runtime.exit_code_for({"status": status} if status else {}) == expected
