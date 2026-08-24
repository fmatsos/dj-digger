"""Acceptance coverage for source-relative M3U8 set copies."""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COPY_SET = ROOT / "references" / "copy-set.sh"
ACID_RAVE_GOLDEN = ROOT / "tests" / "fixtures" / "acid-rave-core.m3u8"


def _emit_m3u8(tracks: list[dict[str, str]], library_root: Path) -> str:
    reference = ROOT / "skills" / "electronic-dj-set-curator" / "references" / "set-emission.md"
    match = re.search(
        r"```python playlist-emission\n(.*?)\n```", reference.read_text(encoding="utf-8"), re.DOTALL
    )
    assert match is not None
    namespace: dict[str, object] = {}
    exec(match.group(1), namespace)
    return namespace["emit_m3u8"](tracks, str(library_root))  # type: ignore[operator]


def _parse_m3u8(playlist: Path) -> list[Path]:
    return [
        Path(line)
        for line in playlist.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]


def _make_noop_chown(tool_directory: Path) -> None:
    """Keep the external script's post-copy ownership step environment-neutral."""
    chown = tool_directory / "chown"
    chown.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    chown.chmod(chown.stat().st_mode | stat.S_IXUSR)


def test_acid_rave_m3u8_remains_copy_set_compatible(tmp_path: Path) -> None:
    library_root = tmp_path / "fixture-library"
    playlist = tmp_path / "generated-acid-rave.m3u8"
    output = tmp_path / "set"
    expected_sources = {
        Path("Acid Rave/01 - Acid Signal.flac"): b"acid signal\n",
        Path("Acid Rave/02 - Warehouse Pressure.flac"): b"warehouse pressure\n",
        Path("Acid Rave/03 - 303 Finale.flac"): b"303 finale\n",
    }
    for relative_path, contents in expected_sources.items():
        source = library_root / relative_path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(contents)

    tracks = [{"source_id": "djing", "path": str(path)} for path in expected_sources]
    playlist.write_text(_emit_m3u8(tracks, library_root), encoding="utf-8")

    assert playlist.read_text(encoding="utf-8") == ACID_RAVE_GOLDEN.read_text(encoding="utf-8")
    for relative_path in _parse_m3u8(playlist):
        assert (library_root / relative_path).is_file()

    source_snapshots = {
        path: (source.read_bytes(), source.stat().st_mtime_ns)
        for path in expected_sources
        if (source := library_root / path).is_file()
    }
    tool_directory = tmp_path / "tools"
    tool_directory.mkdir()
    _make_noop_chown(tool_directory)
    environment = os.environ | {"PATH": f"{tool_directory}:{os.environ['PATH']}"}
    subprocess.run(
        [
            "bash",
            str(COPY_SET),
            "--library",
            str(library_root),
            "--output",
            str(output),
            "--playlist",
            str(playlist),
        ],
        check=True,
        env=environment,
    )

    copied = _parse_m3u8(output / playlist.name)
    assert copied == [
        Path(f"{index:02d} - {path.name}") for index, path in enumerate(expected_sources, 1)
    ]
    for index, (relative_path, expected_contents) in enumerate(expected_sources.items(), 1):
        assert (output / f"{index:02d} - {relative_path.name}").read_bytes() == expected_contents
        source = library_root / relative_path
        assert (source.read_bytes(), source.stat().st_mtime_ns) == source_snapshots[relative_path]
