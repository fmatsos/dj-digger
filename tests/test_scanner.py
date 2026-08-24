from pathlib import Path

import pytest

from dj_digger.config import LibrarySourceConfig
from dj_digger.scanning.scanner import SourceScanner


@pytest.fixture
def source(tmp_path: Path) -> LibrarySourceConfig:
    return LibrarySourceConfig(
        id="library",
        path=tmp_path,
        set_eligible=True,
        analyze=True,
    )


def test_scan_observes_audio_and_all_directories_with_exact_relative_paths(
    source: LibrarySourceConfig,
) -> None:
    (source.path / "Techno").mkdir()
    (source.path / "Techno" / "A.FlAc").write_bytes(b"audio")
    (source.path / "Empty").mkdir()
    (source.path / "notes.txt").write_text("not an audio file")

    result = SourceScanner().scan(source, run_id=1)

    assert set(result.audio_paths) == {"Techno/A.FlAc"}
    assert result.directory_paths == {"Techno", "Empty"}
    assert result.audio_count == 1
    assert result.directory_count == 2
    assert result.artifact_count == 0
    assert result.files_seen == 2
    assert result.audio_seen == 1
    assert result.artifacts_seen == 0


def test_scan_never_opens_source_files_for_writing(
    monkeypatch: pytest.MonkeyPatch, source: LibrarySourceConfig
) -> None:
    audio = source.path / "A.mp3"
    audio.write_bytes(b"audio")
    opened_modes: list[str] = []
    original_open = Path.open

    def spy_open(  # type: ignore[no-untyped-def]
        path: Path, mode: str = "r", *args: object, **kwargs: object
    ):
        if path.is_relative_to(source.path):
            opened_modes.append(mode)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", spy_open)

    SourceScanner().scan(source, run_id=1)

    assert not any(any(flag in mode for flag in "wax+") for mode in opened_modes)
