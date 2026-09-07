"""Public CLI contracts for export and snapshot publications."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dj_digger.cli import app


def _config(tmp_path: Path) -> Path:
    source = tmp_path / "library"
    source.mkdir()
    config = tmp_path / "config.toml"
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
                "analyze = false",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def test_export_command_preserves_json_contract_and_artifact_state(tmp_path: Path) -> None:
    config = _config(tmp_path)

    result = CliRunner().invoke(
        app,
        ["export", "--config", str(config), "--facet", "tracks", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {
        "event": "export",
        "status": "succeeded",
        "exports": [str(tmp_path / "exports" / "tracks.tsv")],
    }
    assert (tmp_path / "exports" / "tracks.tsv").is_file()


def test_snapshot_command_preserves_json_contract_and_artifact_state(tmp_path: Path) -> None:
    config = _config(tmp_path)
    output = tmp_path / "snapshot"

    result = CliRunner().invoke(
        app,
        ["snapshot", "--config", str(config), "--output", str(output), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {
        "event": "snapshot",
        "status": "succeeded",
        "directory": str(output),
        "archive": None,
    }
    assert (output / "snapshot-manifest.json").is_file()
