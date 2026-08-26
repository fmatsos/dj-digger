from pathlib import Path

from typer.testing import CliRunner

from dj_digger.cli import app


def test_copy_help_exposes_script_options_and_owner() -> None:
    result = CliRunner().invoke(app, ["copy", "--help"])

    assert result.exit_code == 0
    for option in ("--library", "--output", "--playlist", "--track", "--verbose", "--owner"):
        assert option in result.output

    short = CliRunner().invoke(app, ["copy", "-h"])
    assert short.exit_code == 0
    assert "--owner" in short.output


def test_copy_requires_playlist_or_track(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()

    result = CliRunner().invoke(
        app, ["copy", "--library", str(library), "--output", str(tmp_path / "output")]
    )

    assert result.exit_code == 2
    assert "At least one --playlist or --track is required" in result.output


def test_copy_rejects_more_than_one_playlist(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    first = tmp_path / "first.m3u8"
    second = tmp_path / "second.m3u8"
    first.write_text("#EXTM3U\n", encoding="utf-8")
    second.write_text("#EXTM3U\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "copy",
            "--library",
            str(library),
            "--output",
            str(tmp_path / "output"),
            "--playlist",
            str(first),
            "--playlist",
            str(second),
        ],
    )

    assert result.exit_code == 2
    assert "Only one --playlist may be provided" in result.output


def test_copy_command_accepts_repeated_tracks_owner_and_local_verbose(
    tmp_path: Path, monkeypatch
) -> None:
    library = tmp_path / "library"
    library.mkdir()
    (library / "one.flac").write_bytes(b"one")
    (library / "two.flac").write_bytes(b"two")
    output = tmp_path / "output"
    ownership: list[tuple[Path, int, int]] = []
    monkeypatch.setattr("dj_digger.set_copy._resolve_owner", lambda _owner: (123, 456))
    monkeypatch.setattr(
        "dj_digger.set_copy._set_recursive_ownership",
        lambda path, uid, gid: ownership.append((path, uid, gid)),
    )

    result = CliRunner().invoke(
        app,
        [
            "copy",
            "--library",
            str(library),
            "--output",
            str(output),
            "--track",
            "one.flac",
            "-t",
            "two.flac",
            "--owner",
            "dj:music",
            "-v",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "COPY 01/2" in result.output
    assert "OWNERSHIP dj:music" in result.output
    assert "Playlist:" in result.output
    assert "[  0%] (0/2)" in result.output
    assert ownership == [(output.resolve(), 123, 456)]


def test_copy_accepts_file_uri_track(tmp_path: Path, monkeypatch) -> None:
    library = tmp_path / "library"
    library.mkdir()
    track = library / "track.flac"
    track.write_bytes(b"audio")
    output = tmp_path / "output"
    monkeypatch.setattr("dj_digger.set_copy._resolve_owner", lambda _owner: (123, 456))
    monkeypatch.setattr("dj_digger.set_copy._set_recursive_ownership", lambda *_args: None)

    result = CliRunner().invoke(
        app,
        [
            "copy",
            "--library",
            str(library),
            "--output",
            str(output),
            "--track",
            track.as_uri(),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output / "01 - track.flac").read_bytes() == b"audio"


def test_copy_rejects_remote_track_uri_before_creating_output(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    output = tmp_path / "output"

    result = CliRunner().invoke(
        app,
        [
            "copy",
            "--library",
            str(library),
            "--output",
            str(output),
            "--track",
            "s3://bucket/track.flac",
        ],
    )

    assert result.exit_code == 1
    assert "Remote playlist entries are not supported: s3://bucket/track.flac" in result.output
    assert not output.exists()


def test_copy_defaults_owner_to_share_share(tmp_path: Path, monkeypatch) -> None:
    library = tmp_path / "library"
    library.mkdir()
    (library / "track.flac").write_bytes(b"audio")
    playlist = tmp_path / "selection.m3u8"
    playlist.write_text("track.flac\n", encoding="utf-8")
    ownership: list[str] = []
    monkeypatch.setattr("dj_digger.set_copy._resolve_owner", lambda _owner: (123, 456))
    monkeypatch.setattr(
        "dj_digger.set_copy._set_recursive_ownership",
        lambda _path, _uid, _gid: ownership.append("share:share"),
    )

    result = CliRunner().invoke(
        app,
        [
            "copy",
            "-l",
            str(library),
            "-o",
            str(tmp_path / "output"),
            "-p",
            str(playlist),
        ],
    )

    assert result.exit_code == 0, result.output
    assert ownership == ["share:share"]


def test_copy_progress_only_advances_after_success(tmp_path: Path, monkeypatch) -> None:
    library = tmp_path / "library"
    library.mkdir()
    (library / "track.flac").write_bytes(b"audio")
    monkeypatch.setattr("dj_digger.set_copy._resolve_owner", lambda _owner: (1, 2))
    monkeypatch.setattr(
        "dj_digger.set_copy._copy_track_atomic",
        lambda *args: (_ for _ in ()).throw(OSError("boom")),
    )

    result = CliRunner().invoke(
        app,
        ["copy", "-l", str(library), "-o", str(tmp_path / "output"), "-t", "track.flac", "-v"],
    )

    assert result.exit_code == 1
    assert "[  0%] (0/1)" in result.output
    assert "COPY 01/1" in result.output
    assert "100%" not in result.output
