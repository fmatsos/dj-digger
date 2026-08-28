from pathlib import Path

import pytest
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


def test_analyze_propagates_selection_and_execution_options(monkeypatch, tmp_path: Path) -> None:
    received: dict[str, object] = {}

    def analyze(
        self,
        source_id=None,
        *,
        path_prefix=None,
        limit=None,
        force=False,
        workers=1,
        track_timeout=1800.0,
        progress=None,
    ):
        received.update(
            source_id=source_id,
            path_prefix=path_prefix,
            limit=limit,
            force=force,
            workers=workers,
            track_timeout=track_timeout,
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
            "--track-timeout",
            "12.5",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert received == {
        "source_id": "library",
        "path_prefix": "House",
        "limit": 2,
        "force": True,
        "workers": 3,
        "track_timeout": 12.5,
    }
    assert '"event":"analyze"' in result.output


def test_analyze_uses_safe_execution_defaults(monkeypatch, tmp_path: Path) -> None:
    received: dict[str, object] = {}

    def analyze(self, source_id=None, **options):
        received.update(options)
        return type(
            "Result",
            (),
            {"__dict__": {"eligible": 0, "analyzed": 0, "reused": 0, "failed": 0}},
        )()

    monkeypatch.setattr("dj_digger.cli.WorkspaceApplication.analyze", analyze)

    result = CliRunner().invoke(app, ["analyze", "--config", str(_config(tmp_path))])

    assert result.exit_code == 0
    assert received["workers"] == 1
    assert received["track_timeout"] == 1800.0


def test_analyze_installs_rich_progress_reporter(monkeypatch, tmp_path: Path) -> None:
    events: list[object] = []

    class Progress:
        def __init__(self, *, verbosity: int):
            events.append(("created", verbosity))

        def __enter__(self):
            events.append("entered")
            return self

        def __exit__(self, *args):
            events.append("exited")

    def analyze(self, source_id=None, *, progress=None, **options):
        events.append(("analyze", progress))
        return type("Result", (), {"__dict__": {"failed": 0, "analyzed": 0}})()

    monkeypatch.setattr("dj_digger.cli.RichProgressReporter", Progress)
    monkeypatch.setattr("dj_digger.cli.WorkspaceApplication.analyze", analyze)

    result = CliRunner().invoke(app, ["-v", "analyze", "--config", str(_config(tmp_path))])

    assert result.exit_code == 0
    assert events[0:2] == [("created", 1), "entered"]
    assert events[2][0] == "analyze"
    assert events[2][1].__class__ is Progress
    assert events[3] == "exited"


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
def test_analyze_rejects_invalid_track_timeout(tmp_path: Path, value: str) -> None:
    result = CliRunner().invoke(
        app,
        ["analyze", "--config", str(_config(tmp_path)), "--track-timeout", value],
    )

    assert result.exit_code == 2
    assert "must be greater than zero" in result.output


@pytest.mark.parametrize("value", ["0", "-1"])
def test_analyze_rejects_non_positive_workers_before_creating_catalog(
    tmp_path: Path, value: str
) -> None:
    result = CliRunner().invoke(
        app,
        ["analyze", "--config", str(_config(tmp_path)), "--workers", value],
    )

    assert result.exit_code == 2
    assert "must be greater than zero" in result.output
    assert not (tmp_path / "catalog.sqlite").exists()
