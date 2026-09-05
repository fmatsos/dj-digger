import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dj_digger.application import WorkspaceApplication
from dj_digger.cli import app
from dj_digger.config import WorkspaceConfig


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
    result = runner.invoke(app, ["status", "--config", str(config), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["event"] == "status"
    assert payload["sources"][0]["present_tracks"] == 1
    assert payload["sources"][0]["missing_tracks"] == 0


def test_doctor_reports_unavailable_source_root(tmp_path: Path) -> None:
    config = write_config(tmp_path, source=tmp_path / "missing", exports=tmp_path / "exports")

    result = CliRunner().invoke(app, ["doctor", "--config", str(config), "--json"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["event"] == "doctor"
    assert any("source root unavailable" in issue for issue in payload["issues"])


def test_doctor_reports_sqlite_runtime_schema_and_health(tmp_path: Path) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config = write_config(tmp_path, source=source, exports=tmp_path / "exports")

    result = CliRunner().invoke(app, ["doctor", "--config", str(config), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["database"] == str((tmp_path / "catalog.sqlite").resolve())
    assert payload["sqlite_version"]
    assert payload["migration_version"] == 9
    assert payload["journal_mode"] == "wal"
    assert payload["foreign_keys"] == 1
    assert payload["synchronous"] == 1
    assert payload["busy_timeout_ms"] == 5_000
    assert payload["database_size_bytes"] > 0
    assert payload["wal_size_bytes"] >= 0
    assert isinstance(payload["shm_present"], bool)
    assert payload["page_count"] > 0
    assert payload["page_size_bytes"] > 0
    assert payload["freelist_count"] >= 0
    assert payload["quick_check"] == "ok"
    assert payload["issues"] == []


@pytest.mark.parametrize(
    ("setting", "value", "expected_issue"),
    (
        ("foreign_keys", "OFF", "SQLite foreign keys are disabled"),
        ("journal_mode", "DELETE", "SQLite journal mode is delete, expected wal"),
        ("user_version", "7", "SQLite migration version is 7, expected 9"),
    ),
)
def test_doctor_marks_unhealthy_sqlite_settings_as_issues(
    tmp_path: Path, setting: str, value: str, expected_issue: str
) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config_path = write_config(tmp_path, source=source, exports=tmp_path / "exports")

    with WorkspaceApplication(WorkspaceConfig.load(config_path)) as application:
        application.database.execute(f"PRAGMA {setting} = {value}")
        diagnostic = application.doctor()

    assert diagnostic["status"] == "failed"
    assert expected_issue in diagnostic["issues"]


def test_doctor_marks_failed_quick_check_as_an_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config_path = write_config(tmp_path, source=source, exports=tmp_path / "exports")

    with WorkspaceApplication(WorkspaceConfig.load(config_path)) as application:
        monkeypatch.setattr(application.database, "quick_check", lambda: "corrupt page")
        diagnostic = application.doctor()

    assert diagnostic["status"] == "failed"
    assert "SQLite quick check failed: corrupt page" in diagnostic["issues"]


def test_doctor_flags_ffmpeg_missing_the_chromaprint_muxer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config_path = write_config(tmp_path, source=source, exports=tmp_path / "exports")

    with WorkspaceApplication(WorkspaceConfig.load(config_path)) as application:
        monkeypatch.setattr("dj_digger.application._has_chromaprint_muxer", lambda: False)
        diagnostic = application.doctor()

    assert diagnostic["status"] == "failed"
    assert "ffmpeg is missing the chromaprint muxer required for duplicates" in diagnostic["issues"]


def test_doctor_skips_chromaprint_check_when_no_source_is_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config_path = tmp_path / "dj-digger.toml"
    config_path.write_text(
        "\n".join(
            [
                "[workspace]",
                'database = "catalog.sqlite"',
                f'exports = "{tmp_path / "exports"}"',
                "",
                "[[library.sources]]",
                'id = "required"',
                f'path = "{source}"',
                "set_eligible = true",
                "analyze = false",
                "enabled = false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with WorkspaceApplication(WorkspaceConfig.load(config_path)) as application:
        monkeypatch.setattr("dj_digger.application._has_chromaprint_muxer", lambda: False)
        diagnostic = application.doctor()

    assert not any("chromaprint" in issue for issue in diagnostic["issues"])


def test_doctor_treats_absent_wal_and_shm_files_as_information(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "music"
    source.mkdir()
    config_path = write_config(tmp_path, source=source, exports=tmp_path / "exports")

    with WorkspaceApplication(WorkspaceConfig.load(config_path)) as application:
        diagnostics = application.database.diagnostics()
        diagnostics["wal_size_bytes"] = 0
        diagnostics["shm_present"] = False
        monkeypatch.setattr(application.database, "diagnostics", lambda: diagnostics)
        diagnostic = application.doctor()

    assert diagnostic["status"] == "succeeded"
    assert diagnostic["issues"] == []
    assert diagnostic["wal_size_bytes"] == 0
    assert diagnostic["shm_present"] is False


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
