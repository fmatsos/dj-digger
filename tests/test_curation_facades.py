from __future__ import annotations

from importlib import import_module

import pytest


@pytest.mark.parametrize(
    ("legacy_name", "canonical_name"),
    (
        ("dj_digger.curation", "dj_digger.core.curation"),
        ("dj_digger.curation.agent", "dj_digger.core.curation.agent"),
        ("dj_digger.curation.catalog", "dj_digger.core.curation.catalog"),
        ("dj_digger.curation.client", "dj_digger.core.curation.client"),
        ("dj_digger.curation.models", "dj_digger.core.curation.models"),
        ("dj_digger.curation.prompts", "dj_digger.core.curation.prompts"),
        ("dj_digger.curation.repository", "dj_digger.core.curation.repository"),
        ("dj_digger.curation.validation", "dj_digger.core.curation.validation"),
        ("dj_digger.mcp_server", "dj_digger.core.mcp_server"),
    ),
)
def test_legacy_curation_exports_preserve_canonical_identity(
    legacy_name: str, canonical_name: str
) -> None:
    legacy = import_module(legacy_name)
    canonical = import_module(canonical_name)
    assert legacy.__all__ == canonical.__all__
    for name in canonical.__all__:
        assert getattr(legacy, name) is getattr(canonical, name), (legacy_name, name)
