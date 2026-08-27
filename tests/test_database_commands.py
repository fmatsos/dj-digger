import json
from pathlib import Path

from typer.testing import CliRunner

from dj_digger.catalog.database import Database
from dj_digger.cli import app


def _write_config(tmp_path: Path) -> Path:
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
                "analyze = false",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def _payload(result) -> dict[str, object]:
    assert result.exception is None
    return json.loads(result.output)


def test_database_reports_runtime_file_and_health_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"

    with Database.open(path) as database:
        database.migrate()
        diagnostics = database.diagnostics()

    assert diagnostics["path"] == str(path.resolve())
    assert diagnostics["sqlite_version"]
    assert diagnostics["schema_version"] == 7
    assert diagnostics["journal_mode"] == "wal"
    assert diagnostics["foreign_keys"] == 1
    assert diagnostics["synchronous"] == 1
    assert diagnostics["busy_timeout_ms"] == 5_000
    assert diagnostics["file_size_bytes"] > 0
    assert diagnostics["wal_size_bytes"] >= 0
    assert isinstance(diagnostics["shm_present"], bool)
    assert diagnostics["page_count"] > 0
    assert diagnostics["page_size_bytes"] > 0
    assert diagnostics["freelist_count"] >= 0
    assert diagnostics["quick_check"] == "ok"


def test_database_check_primitives_report_success(tmp_path: Path) -> None:
    with Database.open(tmp_path / "catalog.sqlite") as database:
        database.migrate()

        database.optimize()

        assert database.quick_check() == "ok"
        assert database.integrity_check() == ["ok"]


def test_database_maintenance_commands_return_structured_json(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    runner = CliRunner()

    optimize = runner.invoke(app, ["database", "optimize", "--config", str(config)])
    quick_check = runner.invoke(app, ["database", "quick-check", "--config", str(config)])
    integrity_check = runner.invoke(
        app, ["database", "integrity-check", "--config", str(config)]
    )

    assert optimize.exit_code == 0
    assert _payload(optimize) == {"event": "database.optimize", "status": "succeeded"}
    assert quick_check.exit_code == 0
    assert _payload(quick_check) == {
        "event": "database.quick-check",
        "quick_check": "ok",
        "status": "succeeded",
    }
    assert integrity_check.exit_code == 0
    assert _payload(integrity_check) == {
        "event": "database.integrity-check",
        "integrity_check": ["ok"],
        "status": "succeeded",
    }


def test_database_rebuild_current_analysis_reports_projected_count(tmp_path: Path) -> None:
    config = _write_config(tmp_path)

    result = CliRunner().invoke(
        app, ["database", "rebuild-current-analysis", "--config", str(config)]
    )

    assert result.exit_code == 0
    assert _payload(result) == {
        "event": "database.rebuild-current-analysis",
        "projected_tracks": 0,
        "status": "succeeded",
    }
