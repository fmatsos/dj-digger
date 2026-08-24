"""V1B acceptance: Curator availability comes only from canonical tracks.tsv."""

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dj_digger.application import WorkspaceApplication
from dj_digger.catalog.models import Track
from dj_digger.config import WorkspaceConfig
from dj_digger.metadata.exiftool import MetadataRunResult, MetadataService


@dataclass(frozen=True)
class CuratorCandidate:
    """The Curator's source-aware inventory identity from its public contract."""

    source_id: str
    track_id: int
    path: str


def _generate_known_set(tracks_path: Path) -> tuple[CuratorCandidate, ...]:
    """Resolve the deterministic V1B set only from the published tracks facet."""
    with tracks_path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        candidates = tuple(
            CuratorCandidate(
                source_id=row["source_id"], track_id=int(row["track_id"]), path=row["path"]
            )
            for row in rows
            if row["set_eligible"] == "true"
        )
    return tuple(candidate for candidate in candidates if candidate.path == "Techno/Known.flac")


def _write_v1b_config(tmp_path: Path, djing: Path, music: Path) -> Path:
    config = tmp_path / "dj-digger.toml"
    config.write_text(
        "\n".join(
            (
                "[workspace]",
                'database = "catalog.sqlite"',
                'exports = "exports"',
                "",
                "[export]",
                "legacy_compatibility = false",
                "",
                "[[library.sources]]",
                'id = "djing"',
                f'path = "{djing}"',
                "set_eligible = true",
                "analyze = true",
                "",
                "[[library.sources]]",
                'id = "music"',
                f'path = "{music}"',
                "set_eligible = false",
                "analyze = false",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def _analysis(track: Track) -> Mapping[str, object]:
    return {"path": track.relative_path}


def test_v1b_refresh_resolves_known_curator_set_without_legacy_inventory(
    tmp_path: Path, monkeypatch
) -> None:
    djing = tmp_path / "fixture-library" / "djing" / "Techno"
    music = tmp_path / "fixture-library" / "music" / "Archive"
    djing.mkdir(parents=True)
    music.mkdir(parents=True)
    (djing / "Known.flac").write_bytes(b"fixture audio")
    (music / "NotEligible.flac").write_bytes(b"fixture audio")
    config = WorkspaceConfig.load(_write_v1b_config(tmp_path, djing.parent, music.parent))
    monkeypatch.setattr(
        MetadataService, "refresh", lambda *_args, **_kwargs: MetadataRunResult(0, 0, 2)
    )

    refresh = WorkspaceApplication(config, analysis_extractor=_analysis).refresh()

    assert refresh["status"] == "succeeded"
    assert not (config.exports / "djing-files.tsv").exists()
    assert not (config.exports / "music-files.tsv").exists()
    assert _generate_known_set(config.exports / "tracks.tsv") == (
        CuratorCandidate(source_id="djing", track_id=1, path="Techno/Known.flac"),
    )
