"""CLI exit-code and diagnostic contract for run commands."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from dj_digger.application import WorkspaceApplication
from dj_digger.cli import app


def _config(tmp_path: Path) -> Path:
    source = tmp_path / "music"
    source.mkdir()
    config = tmp_path / "dj-digger.toml"
    config.write_text(
        "\n".join(
            (
                "[workspace]",
                'database = "catalog.sqlite"',
                'exports = "exports"',
                "",
                "[[library.sources]]",
                'id = "library"',
                f'path = "{source}"',
                "set_eligible = true",
                "analyze = true",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return config


@pytest.mark.parametrize("command", ("metadata", "analyze"))
@pytest.mark.parametrize(("status", "exit_code"), (("succeeded", 0), ("partial", 2), ("failed", 1)))
def test_extract_commands_map_status_to_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    status: str,
    exit_code: int,
) -> None:
    result = (
        SimpleNamespace(status=status, extracted=1, failed=0, skipped=0)
        if command == "metadata"
        else SimpleNamespace(status=status, eligible=1, analyzed=1, reused=0, failed=0)
    )
    monkeypatch.setattr(WorkspaceApplication, command, lambda *_args, **_kwargs: result)

    response = CliRunner().invoke(app, [command, "--config", str(_config(tmp_path)), "--json"])

    assert response.exit_code == exit_code
    assert f'"event":"{command}"' in response.output
    assert f'"status":"{status}"' in response.output


@pytest.mark.parametrize(("status", "exit_code"), (("succeeded", 0), ("partial", 2), ("failed", 1)))
def test_refresh_maps_status_to_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: str,
    exit_code: int,
) -> None:
    monkeypatch.setattr(
        "dj_digger.cli.WorkspaceApplication.refresh",
        lambda *_args, **_kwargs: {"event": "refresh", "status": status},
    )

    response = CliRunner().invoke(app, ["refresh", "--config", str(_config(tmp_path)), "--json"])

    assert response.exit_code == exit_code
    assert response.output.strip() == f'{{"event":"refresh","status":"{status}"}}'
