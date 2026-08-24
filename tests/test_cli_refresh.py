from pathlib import Path

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
