from pathlib import Path

from typer.testing import CliRunner

from dj_digger.cli import app


def _config(tmp_path: Path) -> Path:
    source = tmp_path / "music"
    source.mkdir()
    config = tmp_path / "dj-digger.toml"
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
                "analyze = true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def test_analyze_exposes_all_selection_options(monkeypatch, tmp_path: Path) -> None:
    received: dict[str, object] = {}

    def analyze(self, source_id=None, *, path_prefix=None, limit=None, force=False, workers=1):
        received.update(
            source_id=source_id,
            path_prefix=path_prefix,
            limit=limit,
            force=force,
            workers=workers,
        )
        return type(
            "Result",
            (),
            {"__dict__": {"eligible": 0, "analyzed": 0, "reused": 0, "failed": 0}},
        )()

    monkeypatch.setattr("dj_digger.cli.WorkspaceApplication.analyze", analyze)

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--config",
            str(_config(tmp_path)),
            "--source",
            "library",
            "--path",
            "House",
            "--limit",
            "2",
            "--force",
            "--workers",
            "3",
        ],
    )

    assert result.exit_code == 0
    assert received == {
        "source_id": "library",
        "path_prefix": "House",
        "limit": 2,
        "force": True,
        "workers": 3,
    }
    assert '"event":"analyze"' in result.output
