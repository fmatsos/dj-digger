from __future__ import annotations

import inspect
from pathlib import Path

from dj_digger.core.application import CoreApplication


def test_core_create_curation_is_awaitable_and_keeps_sync_bridge_out_of_core() -> None:
    assert inspect.iscoroutinefunction(CoreApplication.create_curation)
    source = Path("src/dj_digger/core/application/app.py").read_text(encoding="utf-8")
    assert "asyncio.run(" not in source
