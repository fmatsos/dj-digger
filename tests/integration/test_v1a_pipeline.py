"""Representative V1A pipeline coverage through the public application service."""

import hashlib
import json
import tarfile
from pathlib import Path

from analysis_fixture import analysis_fixture
from jsonschema import Draft202012Validator, FormatChecker

from dj_digger.application import WorkspaceApplication
from dj_digger.config import LibrarySourceConfig, WorkspaceConfig
from dj_digger.exports.snapshot import SnapshotResult

_analysis = analysis_fixture


def _workspace(tmp_path: Path, source: Path) -> WorkspaceConfig:
    return WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=(
            LibrarySourceConfig(
                id="subset", path=source, set_eligible=True, analyze=True, enabled=True
            ),
        ),
    )


def validate_snapshot(snapshot: SnapshotResult) -> bool:
    """Validate the published snapshot against its fixed V1A contract."""
    manifest_path = snapshot.directory / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads(
        (Path(__file__).parents[2] / "schemas" / "snapshot-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
    for facet in manifest["facets"]:
        assert facet["sha256"] == hashlib.sha256(
            (snapshot.directory / facet["relative_path"]).read_bytes()
        ).hexdigest()
    return True


def test_v1a_refresh_reuses_analysis_and_publishes_an_archived_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "library"
    source.mkdir()
    (source / "subset.flac").write_bytes(b"representative audio bytes")
    application = WorkspaceApplication(_workspace(tmp_path, source), analysis_extractor=_analysis)

    first = application.refresh()
    second = application.analyze("subset", force=True)
    snapshot = application.snapshot(tmp_path / "snapshot", archive=True)

    assert first["status"] == "succeeded"
    assert first["analysis"]["analyzed"] == 1
    assert all(
        (application.config.exports / name).is_file()
        for name in ("dj-analysis.tsv", "dj-sections.jsonl", "dj-analysis-run.json")
    )
    assert second.eligible == 1
    assert second.reused == second.eligible
    assert snapshot.archive is not None
    assert snapshot.archive.exists()
    with tarfile.open(snapshot.archive, "r:gz") as archive:
        assert "snapshot/snapshot-manifest.json" in archive.getnames()
    assert validate_snapshot(snapshot)
