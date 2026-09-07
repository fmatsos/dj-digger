from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "legacy_name",
    (
        "dj_digger.application",
        "dj_digger.analysis",
        "dj_digger.artifacts",
        "dj_digger.background",
        "dj_digger.catalog",
        "dj_digger.config",
        "dj_digger.curation",
        "dj_digger.duplicates",
        "dj_digger.exports",
        "dj_digger.logging",
        "dj_digger.mcp_server",
        "dj_digger.metadata",
        "dj_digger.progress",
        "dj_digger.resources",
        "dj_digger.rich_progress",
        "dj_digger.scanning",
        "dj_digger.set_copy",
        "dj_digger.terminal",
    ),
)
def test_removed_legacy_module_paths_are_absent(legacy_name: str) -> None:
    source_path = Path("src") / Path(*legacy_name.split("."))
    assert not list(source_path.glob("*.py"))
