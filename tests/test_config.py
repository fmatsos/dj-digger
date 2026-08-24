from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from dj_digger.config import WorkspaceConfig

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_multiple_sources_with_stable_ids() -> None:
    config = WorkspaceConfig.load(FIXTURES / "dj-digger.toml")

    assert [source.id for source in config.sources] == ["djing", "music"]
    assert config.sources[0].set_eligible is True
    assert config.sources[1].analyze is False
    assert config.export.legacy_compatibility is True


def test_resolves_workspace_and_source_paths_from_config_directory() -> None:
    config = WorkspaceConfig.load(FIXTURES / "dj-digger.toml")

    assert config.database == (FIXTURES / "workspace" / "dj-digger.sqlite").resolve()
    assert config.exports == (FIXTURES / "workspace" / "exports").resolve()
    assert config.sources[0].path == (FIXTURES / "library" / "djing").resolve()


def test_shipped_example_uses_compose_writable_workspace_paths() -> None:
    config = WorkspaceConfig.load(Path("config/dj-digger.example.toml"))

    assert config.database == Path("/workspace/dj-digger.sqlite")
    assert config.exports == Path("/workspace/exports")


@pytest.mark.parametrize("fixture_name", ["blank-source-id.toml", "duplicate-source-id.toml"])
def test_rejects_blank_or_duplicate_source_ids(fixture_name: str) -> None:
    with pytest.raises(ValueError, match="source id"):
        WorkspaceConfig.load(FIXTURES / fixture_name)


@pytest.mark.parametrize(
    "fixture_name", ["database-inside-source.toml", "exports-inside-source.toml"]
)
def test_rejects_workspace_state_inside_a_source_root(fixture_name: str) -> None:
    with pytest.raises(ValueError, match="must not be inside source"):
        WorkspaceConfig.load(FIXTURES / fixture_name)


def test_allows_disabling_legacy_compatibility_and_records_are_immutable() -> None:
    config = WorkspaceConfig.load(FIXTURES / "legacy-disabled.toml")

    assert config.export.legacy_compatibility is False
    with pytest.raises(FrozenInstanceError):
        config.sources[0].enabled = False
