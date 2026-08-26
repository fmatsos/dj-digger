from pathlib import Path

import pytest
from typer.testing import CliRunner

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


def test_refresh_does_not_publish_when_required_scan_fails(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    exports.mkdir()
    tracks = exports / "tracks.tsv"
    tracks.write_text("previous export\n", encoding="utf-8")
    config = write_config(tmp_path, source=tmp_path / "missing", exports=exports)

    result = CliRunner().invoke(app, ["refresh", "--config", str(config)])

    assert result.exit_code != 0
    assert tracks.read_text(encoding="utf-8") == "previous export\n"
    assert '"event":"refresh"' in result.output
    assert '"status":"failed"' in result.output


def test_scan_accepts_a_single_source_filter(tmp_path: Path) -> None:
    source = tmp_path / "music"
    source.mkdir()
    (source / "one.mp3").write_bytes(b"audio")
    config = write_config(tmp_path, source=source, exports=tmp_path / "exports")

    result = CliRunner().invoke(app, ["scan", "--config", str(config), "--source", "required"])

    assert result.exit_code == 0
    assert '"event":"scan"' in result.output
    assert '"status":"succeeded"' in result.output


def test_refresh_passes_the_live_reporter_to_the_application(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config = write_config(tmp_path, source=source, exports=tmp_path / "exports")
    reporter = object()
    received: list[object] = []

    class ReporterContext:
        def __init__(self, *, verbosity: int = 0):
            assert verbosity == 0

        def __enter__(self):
            return reporter

        def __exit__(self, exc_type, exc_value, traceback):
            return None

    def refresh(self, *, progress=None, workers=1, track_timeout=1800.0):
        received.extend([progress, workers, track_timeout])
        return {"event": "refresh", "status": "succeeded", "published": True}

    monkeypatch.setattr("dj_digger.cli.RichProgressReporter", ReporterContext)
    monkeypatch.setattr("dj_digger.cli.WorkspaceApplication.refresh", refresh)

    result = CliRunner().invoke(
        app,
        [
            "refresh",
            "--config",
            str(config),
            "--workers",
            "3",
            "--track-timeout",
            "12.5",
        ],
    )

    assert result.exit_code == 0
    assert received == [reporter, 3, 12.5]
    assert result.stdout.strip().startswith('{"event":"refresh"')


def test_refresh_uses_safe_execution_defaults(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config = write_config(tmp_path, source=source, exports=tmp_path / "exports")
    received: dict[str, object] = {}

    def refresh(self, **options):
        received.update(options)
        return {"event": "refresh", "status": "succeeded", "published": True}

    monkeypatch.setattr("dj_digger.cli.WorkspaceApplication.refresh", refresh)

    result = CliRunner().invoke(app, ["refresh", "--config", str(config)])

    assert result.exit_code == 0
    assert received["workers"] == 1
    assert received["track_timeout"] == 1800.0


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
def test_refresh_rejects_invalid_track_timeout(tmp_path: Path, value: str) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config = write_config(tmp_path, source=source, exports=tmp_path / "exports")

    result = CliRunner().invoke(
        app,
        ["refresh", "--config", str(config), "--track-timeout", value],
    )

    assert result.exit_code == 2
    assert "must be greater than zero" in result.output


@pytest.mark.parametrize("value", ["0", "-1"])
def test_refresh_rejects_non_positive_workers_before_creating_catalog(
    tmp_path: Path, value: str
) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config = write_config(tmp_path, source=source, exports=tmp_path / "exports")

    result = CliRunner().invoke(
        app,
        ["refresh", "--config", str(config), "--workers", value],
    )

    assert result.exit_code == 2
    assert "must be greater than zero" in result.output
    assert not (tmp_path / "catalog.sqlite").exists()


def test_refresh_global_verbosity_count_is_zero_one_or_two(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config = write_config(tmp_path, source=source, exports=tmp_path / "exports")
    received: list[int] = []

    class ReporterContext:
        def __init__(self, *, verbosity: int = 0):
            received.append(verbosity)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

    monkeypatch.setattr("dj_digger.cli.RichProgressReporter", ReporterContext)
    monkeypatch.setattr(
        "dj_digger.cli.WorkspaceApplication.refresh",
        lambda self, *, progress=None, workers=1, track_timeout=1800.0: {
            "event": "refresh",
            "status": "succeeded",
        },
    )

    for args in (["refresh"], ["-v", "refresh"], ["-vv", "refresh"]):
        result = CliRunner().invoke(app, [*args, "--config", str(config)])
        assert result.exit_code == 0

    assert received == [0, 1, 2]
