from pathlib import Path

from dj_digger.core.application import CoreApplication
from dj_digger.core.application.operations import (
    DatabaseIntegrityCheckResult,
    DatabaseOptimizeResult,
    DatabaseQuickCheckResult,
    DatabaseRebuildResult,
    DoctorResult,
    StatusResult,
)
from dj_digger.core.config import WorkspaceConfig


def _config(tmp_path: Path) -> WorkspaceConfig:
    source = tmp_path / "music"
    source.mkdir()
    path = tmp_path / "config.toml"
    path.write_text(
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
    return WorkspaceConfig.load(path)


def test_core_operations_return_typed_results(tmp_path: Path) -> None:
    with CoreApplication(_config(tmp_path)) as application:
        assert isinstance(application.status(), StatusResult)
        assert isinstance(application.doctor(), DoctorResult)
        assert isinstance(application.optimize_database(), DatabaseOptimizeResult)
        assert isinstance(application.quick_check_database(), DatabaseQuickCheckResult)
        assert isinstance(application.integrity_check_database(), DatabaseIntegrityCheckResult)
        assert isinstance(application.rebuild_current_analysis(), DatabaseRebuildResult)


def test_operation_results_keep_database_health_and_exit_semantics(tmp_path: Path) -> None:
    with CoreApplication(_config(tmp_path)) as application:
        quick_check = application.quick_check_database()
        integrity = application.integrity_check_database()
        doctor = application.doctor()

    assert quick_check.status == "succeeded"
    assert quick_check.quick_check == "ok"
    assert integrity.status == "succeeded"
    assert integrity.integrity_check == ("ok",)
    assert doctor.status == "succeeded"
    assert doctor.issues == ()
