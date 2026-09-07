from __future__ import annotations

from pathlib import Path

from dj_digger.core.application.copy_set import CopySetRequest, CopySetUseCase


def test_copy_set_use_case_publishes_playlist_manifest_and_tracks(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    (library / "track.flac").write_bytes(b"audio")
    playlist = tmp_path / "selection.m3u8"
    playlist.write_text("track.flac\n", encoding="utf-8")
    output = tmp_path / "output"
    events: list[object] = []

    result = CopySetUseCase(ownership_setter=lambda *_args: None).execute(
        CopySetRequest(
            library=library.resolve(),
            output=output,
            playlist=playlist,
            owner="1:2",
        ),
        progress=events.append,
    )

    assert result.total == 1
    assert result.playlist == output / "selection.m3u8"
    assert result.text_list == output / "selection.txt"
    assert (output / "01 - track.flac").read_bytes() == b"audio"
    assert result.playlist.read_text(encoding="utf-8") == "#EXTM3U\n01 - track.flac\n"
    assert result.text_list.read_text(encoding="utf-8").startswith("ORDER\tGROUP\tFILE\tSOURCE\n")
    assert events
