"""Tranche 5 acceptance through the public workspace/CLI contract."""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from analysis_fixture import analysis_fixture
from test_audit_parity import _old_directory_stats, _old_inventory_rows
from typer.testing import CliRunner

from dj_digger.application import WorkspaceApplication
from dj_digger.cli import app
from dj_digger.config import WorkspaceConfig

PARITY_LIBRARY = Path(__file__).resolve().parents[1] / "fixtures" / "parity-library"


def _write_config(path: Path, source: Path, *, legacy: bool, exports: str) -> Path:
    config = path / "workspace.toml"
    config.write_text(
        "\n".join(
            (
                "[workspace]",
                'database = "catalog.sqlite"',
                f'exports = "{exports}"',
                "",
                "[export]",
                f"legacy_compatibility = {str(legacy).lower()}",
                "",
                "[[library.sources]]",
                'id = "music"',
                f'path = "{source}"',
                "set_eligible = true",
                "analyze = true",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return config


@pytest.mark.skipif(
    any(shutil.which(binary) is None for binary in ("exiftool", "ffmpeg", "ffprobe")),
    reason="tranche 5 requires real ExifTool and FFmpeg binaries",
)
def test_public_workspace_rebuilds_parity_and_canonical_facets(tmp_path: Path) -> None:
    source = tmp_path / "library"
    shutil.copytree(PARITY_LIBRARY, source)
    tagged = source / "Audio" / "acceptance.mp3"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.25",
            "-metadata", "title=Tranche 5", "-codec:a", "libmp3lame", str(tagged),
        ],
        check=True,
        capture_output=True,
    )
    config_path = _write_config(tmp_path, source, legacy=True, exports="exports-legacy")
    runner = CliRunner()

    scan = runner.invoke(app, ["scan", "--config", str(config_path)])
    metadata = runner.invoke(app, ["metadata", "--config", str(config_path)])
    assert scan.exit_code == 0, scan.output
    assert metadata.exit_code == 0, metadata.output

    config = WorkspaceConfig.load(config_path)
    application = WorkspaceApplication(config, analysis_extractor=analysis_fixture)
    catalog_row = application.database.execute(
        "SELECT relative_path, title FROM tracks "
        "JOIN embedded_metadata ON embedded_metadata.track_id = tracks.id "
        "WHERE source_id = ? AND relative_path = ?",
        ("music", "Audio/acceptance.mp3"),
    ).fetchone()
    assert catalog_row == ("Audio/acceptance.mp3", "Tranche 5")
    analysis = application.analyze(force=True)
    assert analysis.status == "succeeded"

    export = runner.invoke(app, ["export", "--config", str(config_path), "--facet", "all"])
    assert export.exit_code == 0, export.output
    output = config.exports

    # Real FFmpeg/ffprobe execution is part of the public fixture acceptance.
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(tagged)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(probe.stdout)["streams"][0]["codec_type"] == "audio"
    metadata_rows = list(csv.DictReader((output / "music-metadata.csv").open(encoding="utf-8")))
    tagged_row = next(row for row in metadata_rows if row["SourceFile"] == "Audio/acceptance.mp3")
    assert tagged_row["Title"] == "Tranche 5"

    historical_rows = _old_inventory_rows(source)
    historical_paths = {row["path"] for row in historical_rows}
    files = list(
        csv.DictReader((output / "music-files.tsv").open(encoding="utf-8"), delimiter="\t")
    )
    assert {row["path"] for row in files} == historical_paths
    actual_stats = [
        (int(row["level"]), row["path"], int(row["tracks"]))
        for row in csv.DictReader(
            (output / "music-directory-stats.tsv").open(encoding="utf-8"), delimiter="\t"
        )
    ]
    assert actual_stats == _old_directory_stats(historical_rows)

    assert (output / "tracks.tsv").is_file()
    assert all(
        (output / name).is_file()
        for name in ("dj-analysis.tsv", "dj-sections.jsonl", "dj-analysis-run.json")
    )

    canonical_config_path = _write_config(
        tmp_path, source, legacy=False, exports="exports-canonical"
    )
    canonical_export = runner.invoke(
        app, ["export", "--config", str(canonical_config_path), "--facet", "all"]
    )
    assert canonical_export.exit_code == 0, canonical_export.output
    canonical = WorkspaceConfig.load(canonical_config_path).exports
    assert (canonical / "tracks.tsv").is_file()
    assert all(
        (canonical / name).is_file()
        for name in ("dj-analysis.tsv", "dj-sections.jsonl", "dj-analysis-run.json")
    )
    assert (canonical / "library-artifacts.tsv").is_file()
    assert not any(path.name.startswith("music-") for path in canonical.iterdir())

    invalid = runner.invoke(
        app, ["export", "--config", str(canonical_config_path), "--facet", "unknown"]
    )
    assert invalid.exit_code == 1
