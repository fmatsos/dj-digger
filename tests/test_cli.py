from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from dj_digger.cli import _run, app


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
