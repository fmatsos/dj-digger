import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from dj_digger.cli import _run, app


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
    assert "Catalog and export DJ music libraries." in result.output


def test_no_command_displays_help_and_available_commands() -> None:
    result = CliRunner().invoke(app)

    assert result.exit_code == 0
    assert "Catalog and export DJ music libraries." in result.output
    assert "Commands" in result.output
    assert "analyze" in result.output
    assert "refresh" in result.output
    assert "duplicates" in result.output
    assert "jobs" in result.output


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
    assert '"event":"status"' in result.output


def test_status_falls_back_to_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    _write_config(home / ".dj-digger")
    monkeypatch.chdir(workspace)

    result = CliRunner().invoke(app, ["status", "--json"], env={"HOME": str(home)})

    assert result.exit_code == 0
    assert '"event":"status"' in result.output


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
    assert "--config" in result.output


def test_run_closes_its_application_when_the_action_fails(monkeypatch) -> None:
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
    monkeypatch.setattr("dj_digger.cli.WorkspaceConfig.load", lambda _path: config)
    monkeypatch.setattr("dj_digger.cli.WorkspaceApplication", FakeApplication)
    monkeypatch.setattr("dj_digger.cli.RunLogger", FakeLogger)

    with pytest.raises(typer.Exit):
        _run(Path("config.toml"), lambda _service: (_ for _ in ()).throw(RuntimeError("boom")))

    assert events == ["created", "entered", "closed"]
