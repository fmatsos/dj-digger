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


def test_status_reports_source_counts_after_scan(tmp_path: Path) -> None:
    source = tmp_path / "music"
    source.mkdir()
    (source / "one.flac").write_bytes(b"audio")
    config = write_config(tmp_path, source=source, exports=tmp_path / "exports")
    runner = CliRunner()

    assert runner.invoke(app, ["scan", "--config", str(config)]).exit_code == 0
    result = runner.invoke(app, ["status", "--config", str(config)])

    assert result.exit_code == 0
    assert '"event":"status"' in result.output
    assert '"present_tracks":1' in result.output
    assert '"missing_tracks":0' in result.output


def test_doctor_reports_unavailable_source_root(tmp_path: Path) -> None:
    config = write_config(tmp_path, source=tmp_path / "missing", exports=tmp_path / "exports")

    result = CliRunner().invoke(app, ["doctor", "--config", str(config)])

    assert result.exit_code != 0
    assert '"event":"doctor"' in result.output
    assert "source root unavailable" in result.output


def test_doctor_checks_dsp_runtime_only_for_active_analysis_source(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config = write_config(tmp_path, source=source, exports=tmp_path / "exports")
    config.write_text(
        config.read_text(encoding="utf-8").replace("analyze = false", "analyze = true"),
        encoding="utf-8",
    )

    monkeypatch.setattr("dj_digger.application.shutil.which", lambda _: "/usr/bin/tool")
    monkeypatch.setattr("dj_digger.application.importlib.util.find_spec", lambda name: None)

    result = CliRunner().invoke(app, ["doctor", "--config", str(config)])

    assert result.exit_code != 0
    assert "dependency unavailable: essentia" in result.output
    assert "DSP configuration" not in result.output
