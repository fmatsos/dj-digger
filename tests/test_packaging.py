from pathlib import Path

import pytest

from dj_digger.core import resources
from dj_digger.core.catalog import migrations


def test_mcp_dependencies_and_factory_are_importable() -> None:
    import mcp
    import pydantic

    from dj_digger.core.mcp_server import create_curation_mcp_server

    assert mcp is not None
    assert pydantic is not None
    assert callable(create_curation_mcp_server)


def test_required_packaged_resource_reports_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    class MissingResource:
        def joinpath(self, *_parts: str) -> "MissingResource":
            return self

        def is_file(self) -> bool:
            return False

    monkeypatch.setattr(resources, "files", lambda _package: MissingResource())

    with pytest.raises(FileNotFoundError, match="dj_digger/core/schemas/missing.json"):
        resources.read_text("core/schemas/missing.json")


def test_required_sql_resource_reports_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    class MissingResource:
        def joinpath(self, *_parts: str) -> "MissingResource":
            return self

        def is_file(self) -> bool:
            return False

    monkeypatch.setattr(migrations, "files", lambda _package: MissingResource())

    with pytest.raises(FileNotFoundError, match="dj_digger.core.catalog/sql/missing.sql"):
        migrations._load_sql("missing.sql")


def test_packaged_resources_are_resolved_without_current_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    assert resources.read_text("analysis.toml").startswith("[meta]\n")
    assert '"$schema"' in resources.read_text("core/schemas/tracks.schema.json")
    assert '"schema_version"' in resources.read_text("core/schemas/curation-result.schema.json")
