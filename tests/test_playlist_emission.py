import re
from pathlib import Path

import pytest

EMISSION_REFERENCE = Path("skills/electronic-dj-set-curator/references/set-emission.md")


def playlist_contract() -> dict[str, object]:
    text = EMISSION_REFERENCE.read_text(encoding="utf-8")
    match = re.search(r"```python playlist-emission\n(.*?)\n```", text, re.DOTALL)
    assert match is not None, "the M3U8 emission contract pseudocode must be executable"
    namespace: dict[str, object] = {}
    exec(match.group(1), namespace)
    return namespace


def track(source_id: str, path: str) -> dict[str, str]:
    return {"source_id": source_id, "path": path}


def test_default_m3u8_rejects_mixed_sources() -> None:
    contract = playlist_contract()

    with pytest.raises(contract["AmbiguousLibraryRoot"]):  # type: ignore[arg-type]
        contract["emit_m3u8"]([track("djing", "A.flac"), track("archive", "B.flac")])  # type: ignore[operator]


def test_m3u8_preserves_exact_source_relative_paths() -> None:
    contract = playlist_contract()

    playlist = contract["emit_m3u8"](  # type: ignore[operator]
        [track("djing", "Acid/A.flac"), track("djing", "Techno/B.mp3")]
    )

    assert playlist == "#EXTM3U\nAcid/A.flac\nTechno/B.mp3\n"
