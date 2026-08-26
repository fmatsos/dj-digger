import importlib.util
import sqlite3
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.config import WorkspaceConfig
from dj_digger.exports.audit import AuditExporter


def test_removed_legacy_python_interfaces_are_absent() -> None:
    import dj_digger.analysis.persistence as persistence
    import dj_digger.catalog.repositories as repositories

    assert importlib.util.find_spec("dj_digger.exports.legacy") is None
    assert not hasattr(persistence.AnalysisPersistence, "persist_run")
    assert not hasattr(persistence.AnalysisPersistence, "store_success")
    assert not hasattr(persistence.AnalysisPersistence, "store_failure")
    assert not hasattr(persistence, "LegacyOutcome")
    assert not hasattr(repositories, "LegacyExportRepository")


def test_workspace_config_rejects_removed_export_table(tmp_path: Path) -> None:
    config_path = tmp_path / "dj-digger.toml"
    config_path.write_text(
        """[workspace]
database = "workspace/catalog.sqlite"
exports = "workspace/exports"

[export]
legacy_compatibility = false

[library]
sources = [
  { id = "music", path = "library", set_eligible = true, analyze = true },
]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"\[export\].*no longer supported"):
        WorkspaceConfig.load(config_path)


def test_fresh_catalog_initializes_consolidated_current_schema(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")

    database.migrate()

    assert database.scalar("PRAGMA user_version") == 6
    assert database.table_exists("library_sources")
    assert database.table_exists("track_sections")
    assert {
        row[1] for row in database.execute("PRAGMA table_info(embedded_metadata)").fetchall()
    } >= {"input_size_bytes", "input_mtime_ns", "normalization_version"}
    assert database.scalar(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' "
        "AND name = 'scan_runs_one_running_per_source'"
    ) == 1
    assert {
        row[2] for row in database.execute("PRAGMA foreign_key_list(track_sections)").fetchall()
    } == {"audio_analysis"}


def test_catalog_version_five_is_rejected_as_unsupported_legacy(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 5")
    connection.close()
    database = Database.open(path)

    with pytest.raises(RuntimeError, match="legacy catalog version 5 is unsupported.*recreate"):
        database.migrate()


def test_unversioned_nonempty_catalog_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE historical_catalog (id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()
    database = Database.open(path)

    with pytest.raises(RuntimeError, match="unversioned nonempty catalog is unsupported.*recreate"):
        database.migrate()


def test_current_catalog_migration_is_a_no_op(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    database.execute("CREATE TABLE migration_sentinel (value TEXT NOT NULL)")
    database.execute("INSERT INTO migration_sentinel VALUES ('preserved')")
    database.commit()

    database.migrate()

    assert database.scalar("PRAGMA user_version") == 6
    assert database.scalar("SELECT value FROM migration_sentinel") == "preserved"


def test_audit_export_publishes_only_canonical_artifact(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    destination = tmp_path / "exports"

    facets = AuditExporter(database).export(destination)

    assert [facet.path.name for facet in facets] == ["library-artifacts.tsv"]
    assert {path.name for path in destination.iterdir()} == {"library-artifacts.tsv"}
