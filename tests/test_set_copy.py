from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

import pytest

from dj_digger.set_copy import _resolve_owner, _set_recursive_ownership, copy_set


def _track(library: Path, relative: str, contents: bytes) -> Path:
    path = library / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    return path


def test_copy_set_preserves_playlist_order_groups_and_appended_tracks(tmp_path: Path) -> None:
    library = tmp_path / "library"
    first = _track(library, "one.flac", b"one")
    second = _track(library, "nested/two.flac", b"two")
    third = _track(library, "three.flac", b"three")
    playlist = tmp_path / "selection.m3u8"
    playlist.write_text(
        "\ufeff#EXTM3U\n#EXTGRP: Closing / Acid \n"
        "one.flac\n# ignored\nnested/two.flac\n",
        encoding="utf-8",
    )
    output = tmp_path / "output"
    ownership: list[tuple[Path, int, int]] = []

    result = copy_set(
        library=library,
        output=output,
        playlist=playlist,
        tracks=[third],
        owner="dj:music",
        owner_resolver=lambda owner: (123, 456),
        ownership_setter=lambda path, uid, gid: ownership.append((path, uid, gid)),
    )

    assert result.total == 3
    assert result.playlist == output / "selection.m3u8"
    assert result.text_list == output / "selection.txt"
    assert result.playlist.read_text(encoding="utf-8") == (
        "#EXTM3U\n#EXTGRP:Closing / Acid\n"
        "Closing / Acid/01 - one.flac\n"
        "Closing / Acid/02 - two.flac\n"
        "Closing / Acid/03 - three.flac\n"
    )
    assert result.text_list.read_text(encoding="utf-8") == (
        "ORDER\tGROUP\tFILE\tSOURCE\n"
        "01\tClosing / Acid\t01 - one.flac\tone.flac\n"
        "02\tClosing / Acid\t02 - two.flac\tnested/two.flac\n"
        "03\tClosing / Acid\t03 - three.flac\tthree.flac\n"
    )
    assert (output / "Closing / Acid/01 - one.flac").read_bytes() == first.read_bytes()
    assert (output / "Closing / Acid/02 - two.flac").read_bytes() == second.read_bytes()
    assert ownership == [(output.resolve(), 123, 456)]


def test_copy_set_without_playlist_uses_default_manifest_names_and_overwrites(
    tmp_path: Path,
) -> None:
    library = tmp_path / "library"
    source = _track(library, "track.flac", b"new")
    output = tmp_path / "output"
    output.mkdir()
    destination = output / "01 - track.flac"
    destination.write_bytes(b"old")

    result = copy_set(
        library=library,
        output=output,
        tracks=[Path("track.flac")],
        owner="share:share",
        owner_resolver=lambda _owner: (1, 2),
        ownership_setter=lambda _path, _uid, _gid: None,
    )

    assert destination.read_bytes() == source.read_bytes()
    assert result.playlist.name == "playlist.m3u8"
    assert result.text_list.name == "playlist.txt"


@pytest.mark.parametrize(
    ("group", "message"),
    [
        ("", "Empty #EXTGRP"),
        ("/absolute", "Absolute #EXTGRP"),
        ("one/../two", "Unsafe #EXTGRP"),
        ("one//two", "Unsafe #EXTGRP"),
    ],
)
def test_copy_set_rejects_unsafe_groups(tmp_path: Path, group: str, message: str) -> None:
    library = tmp_path / "library"
    _track(library, "track.flac", b"audio")
    playlist = tmp_path / "selection.m3u"
    playlist.write_text(f"#EXTGRP:{group}\ntrack.flac\n", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        copy_set(
            library=library,
            output=tmp_path / "output",
            playlist=playlist,
            owner="share:share",
            owner_resolver=lambda _owner: (1, 2),
            ownership_setter=lambda _path, _uid, _gid: None,
        )


def test_copy_set_rejects_output_inside_library_and_tracks_outside_it(tmp_path: Path) -> None:
    library = tmp_path / "library"
    _track(library, "track.flac", b"audio")
    outside = tmp_path / "outside.flac"
    outside.write_bytes(b"outside")

    with pytest.raises(ValueError, match="output must be outside"):
        copy_set(
            library=library,
            output=library / "set",
            tracks=[Path("track.flac")],
            owner="share:share",
            owner_resolver=lambda _owner: (1, 2),
            ownership_setter=lambda _path, _uid, _gid: None,
        )
    with pytest.raises(ValueError, match="Track is outside the library"):
        copy_set(
            library=library,
            output=tmp_path / "output",
            tracks=[outside],
            owner="share:share",
            owner_resolver=lambda _owner: (1, 2),
            ownership_setter=lambda _path, _uid, _gid: None,
        )


def test_copy_set_rejects_remote_missing_and_non_playlist_inputs(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    bad_extension = tmp_path / "selection.txt"
    bad_extension.write_text("https://example.test/track.flac\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"\.m3u or \.m3u8"):
        copy_set(
            library=library,
            output=tmp_path / "output",
            playlist=bad_extension,
            owner="share:share",
            owner_resolver=lambda _owner: (1, 2),
            ownership_setter=lambda _path, _uid, _gid: None,
        )
    playlist = tmp_path / "selection.m3u8"
    playlist.write_text("https://example.test/track.flac\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Remote playlist entries"):
        copy_set(
            library=library,
            output=tmp_path / "output",
            playlist=playlist,
            owner="share:share",
            owner_resolver=lambda _owner: (1, 2),
            ownership_setter=lambda _path, _uid, _gid: None,
        )


def test_copy_set_does_not_follow_a_destination_symlink(tmp_path: Path) -> None:
    library = tmp_path / "library"
    _track(library, "track.flac", b"audio")
    output = tmp_path / "output"
    output.mkdir()
    external = tmp_path / "external.flac"
    external.write_bytes(b"untouched")
    (output / "01 - track.flac").symlink_to(external)

    with pytest.raises(ValueError, match="symbolic link"):
        copy_set(
            library=library,
            output=output,
            tracks=[Path("track.flac")],
            owner="share:share",
            owner_resolver=lambda _owner: (1, 2),
            ownership_setter=lambda _path, _uid, _gid: None,
        )
    assert external.read_bytes() == b"untouched"


def test_copy_set_preserves_source_contents_and_timestamp(tmp_path: Path) -> None:
    library = tmp_path / "library"
    source = _track(library, "track.flac", b"audio")
    os.utime(source, ns=(1_500_000_000, 1_500_000_000))
    before = (source.read_bytes(), source.stat().st_mtime_ns)

    copy_set(
        library=library,
        output=tmp_path / "output",
        tracks=[Path("track.flac")],
        owner="share:share",
        owner_resolver=lambda _owner: (1, 2),
        ownership_setter=lambda _path, _uid, _gid: None,
    )

    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_copy_set_rejects_invalid_owner_before_creating_output(tmp_path: Path) -> None:
    library = tmp_path / "library"
    _track(library, "track.flac", b"audio")
    output = tmp_path / "output"

    with pytest.raises(ValueError, match="USER:GROUP"):
        copy_set(
            library=library,
            output=output,
            tracks=[Path("track.flac")],
            owner="share",
        )

    assert not output.exists()


def test_copy_set_resolves_owner_before_creating_output(tmp_path: Path) -> None:
    library = tmp_path / "library"
    _track(library, "track.flac", b"audio")
    output = tmp_path / "output"

    def unknown_owner(_owner: str) -> tuple[int, int]:
        raise ValueError("unknown user: nobody-here")

    with pytest.raises(ValueError, match="unknown user"):
        copy_set(
            library=library,
            output=output,
            tracks=[Path("track.flac")],
            owner="nobody-here:group",
            owner_resolver=unknown_owner,
        )

    assert not output.exists()


def test_existing_hardlink_is_atomically_replaced_without_modifying_external_file(
    tmp_path: Path,
) -> None:
    library = tmp_path / "library"
    _track(library, "track.flac", b"replacement")
    output = tmp_path / "output"
    output.mkdir()
    external = tmp_path / "external.flac"
    external.write_bytes(b"keep me")
    os.link(external, output / "01 - track.flac")

    copy_set(
        library=library,
        output=output,
        tracks=[Path("track.flac")],
        owner="1:2",
        owner_resolver=lambda _owner: (1, 2),
        ownership_setter=lambda _path, _uid, _gid: None,
    )

    assert external.read_bytes() == b"keep me"
    assert (output / "01 - track.flac").read_bytes() == b"replacement"
    assert os.stat(external).st_ino != os.stat(output / "01 - track.flac").st_ino


def test_atomic_copy_preserves_source_mode_and_mtime(tmp_path: Path) -> None:
    library = tmp_path / "library"
    source = _track(library, "track.flac", b"audio")
    source.chmod(0o640)
    os.utime(source, ns=(1_500_000_000, 1_600_000_000))

    copy_set(
        library=library,
        output=tmp_path / "output",
        tracks=[Path("track.flac")],
        owner="1:2",
        owner_resolver=lambda _owner: (1, 2),
        ownership_setter=lambda _path, _uid, _gid: None,
    )

    destination = tmp_path / "output/01 - track.flac"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o640
    assert destination.stat().st_mtime_ns == 1_600_000_000


def test_copy_set_rejects_existing_non_file_destination(tmp_path: Path) -> None:
    library = tmp_path / "library"
    _track(library, "track.flac", b"audio")
    output = tmp_path / "output"
    (output / "01 - track.flac").mkdir(parents=True)

    with pytest.raises(ValueError, match="not a regular file"):
        copy_set(
            library=library,
            output=output,
            tracks=[Path("track.flac")],
            owner="1:2",
            owner_resolver=lambda _owner: (1, 2),
            ownership_setter=lambda _path, _uid, _gid: None,
        )


def test_interrupted_copy_keeps_existing_destination_and_cleans_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    _track(library, "track.flac", b"replacement")
    output = tmp_path / "output"
    output.mkdir()
    destination = output / "01 - track.flac"
    destination.write_bytes(b"original")

    def interrupted(_source, target, *args, **kwargs):
        target.write(b"partial")
        raise OSError("interrupted")

    monkeypatch.setattr(shutil, "copyfileobj", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        copy_set(
            library=library,
            output=output,
            tracks=[Path("track.flac")],
            owner="1:2",
            owner_resolver=lambda _owner: (1, 2),
            ownership_setter=lambda _path, _uid, _gid: None,
        )

    assert destination.read_bytes() == b"original"
    assert not list(output.glob(".track.*"))


def test_crlf_file_uri_remote_scheme_and_group_transitions(tmp_path: Path) -> None:
    library = tmp_path / "library"
    first = _track(library, "one.flac", b"one")
    _track(library, "two.flac", b"two")
    playlist = tmp_path / "selection.m3u8"
    playlist.write_bytes((
        f"#EXTM3U\r\n#EXTGRP:First\r\nfile://{first}\r\n"
        "#EXTGRP:Second\r\ntwo.flac\r\n"
    ).encode())

    result = copy_set(
        library=library,
        output=tmp_path / "output",
        playlist=playlist,
        owner="1:2",
        owner_resolver=lambda _owner: (1, 2),
        ownership_setter=lambda _path, _uid, _gid: None,
    )
    assert result.playlist.read_text() == (
        "#EXTM3U\n#EXTGRP:First\nFirst/01 - one.flac\n"
        "#EXTGRP:Second\nSecond/02 - two.flac\n"
    )

    playlist.write_text("s3://bucket/track.flac\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Remote playlist entries"):
        copy_set(
            library=library,
            output=tmp_path / "other",
            playlist=playlist,
            owner="1:2",
            owner_resolver=lambda _owner: (1, 2),
        )


def test_recursive_ownership_never_follows_symlinks(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "file").write_text("data")
    external = tmp_path / "external"
    external.write_text("external")
    (output / "link").symlink_to(external)
    calls: list[tuple[object, bool]] = []

    def record_chown(path, uid, gid, *, dir_fd=None, follow_symlinks=True):
        calls.append((path, follow_symlinks))

    monkeypatch.setattr(os, "chown", record_chown)
    _set_recursive_ownership(output, 12, 34)

    assert calls
    assert all(follow is False for _path, follow in calls)


def test_group_directory_symlink_cannot_escape_output(tmp_path: Path) -> None:
    library = tmp_path / "library"
    _track(library, "track.flac", b"audio")
    output = tmp_path / "output"
    output.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (output / "group").symlink_to(external, target_is_directory=True)
    playlist = tmp_path / "selection.m3u8"
    playlist.write_text("#EXTGRP:group\ntrack.flac\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsafe #EXTGRP"):
        copy_set(
            library=library,
            output=output,
            playlist=playlist,
            owner="1:2",
            owner_resolver=lambda _owner: (1, 2),
        )
    assert not list(external.iterdir())


def test_owner_resolver_supports_numeric_ids_and_reports_unknown_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _resolve_owner("123:456") == (123, 456)

    import pwd

    monkeypatch.setattr(pwd, "getpwnam", lambda _name: (_ for _ in ()).throw(KeyError()))
    with pytest.raises(ValueError, match="unknown user: absent"):
        _resolve_owner("absent:456")
