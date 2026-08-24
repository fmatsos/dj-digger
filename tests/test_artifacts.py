from pathlib import Path

from dj_digger.config import LibrarySourceConfig
from dj_digger.scanning.scanner import SourceScanner


def test_scan_classifies_supported_dj_artifacts_and_serato_contents(tmp_path: Path) -> None:
    paths = {
        "Traktor/collection.nml": "traktor_nml",
        "Traktor/controller.tsi": "traktor_tsi",
        "Playlists/set.M3U8": "playlist_m3u8",
        "Playlists/set.pls": "playlist_pls",
        "Cue/intro.cue": "cue",
        "Metadata/export.XML": "xml",
        "Databases/database V2": "database",
        "_Serato_/Subcrates/Acid.crate": "serato_crate",
        "_Serato_/Database V2": "serato_internal",
    }
    for relative_path in paths:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"metadata")
    source = LibrarySourceConfig("library", tmp_path, set_eligible=True, analyze=True)

    result = SourceScanner().scan(source, run_id=1)

    assert {path: artifact.type for path, artifact in result.artifacts.items()} == paths
    assert result.artifact_count == len(paths)
