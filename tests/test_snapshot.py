import hashlib
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import SourceRepository
from dj_digger.exports.snapshot import SnapshotExporter


def test_snapshot_contains_hashed_canonical_facets_and_archive(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    with database.transaction():
        SourceRepository(database).upsert(
            "src", tmp_path / "music", set_eligible=True, analyze=True, enabled=True
        )
    database.execute(
        "INSERT INTO scan_runs (source_id, started_at, status, scanner_version) "
        "VALUES ('src', 'now', 'succeeded', 'test')"
    )
    run_id = database.scalar("SELECT id FROM scan_runs WHERE source_id = 'src'")
    database.execute(
        """
        INSERT INTO tracks (
            source_id, relative_path, filename, extension, size_bytes, mtime_ns,
            presence_status, discovered_at, last_seen_at, created_scan_id, last_seen_scan_id
        ) VALUES ('src', 'song.flac', 'song.flac', '.flac', 12, 1700000000000000000,
                  'present', 'now', 'now', ?, ?)
        """,
        (run_id, run_id),
    )
    database.commit()

    result = SnapshotExporter(database).create(tmp_path / "snapshot", archive=True)

    manifest_path = result.directory / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    Draft202012Validator(json.loads(Path("schemas/snapshot-manifest.schema.json").read_text())).validate(
        manifest
    )
    facets = {facet["name"]: facet for facet in manifest["facets"]}
    assert set(facets) == {"tracks.tsv", "library-artifacts.tsv"}
    for name, facet in facets.items():
        assert facet["relative_path"] == name
        assert facet["sha256"] == hashlib.sha256(
            (result.directory / name).read_bytes()
        ).hexdigest()
    assert manifest["sources"] == [
        {
            "source_id": "src",
            "root_path": str(tmp_path / "music"),
            "last_successful_scan_id": None,
        }
    ]
    assert result.archive is not None
    assert result.archive.name == "snapshot.tar.gz"
    with tarfile.open(result.archive, "r:gz") as archive:
        assert archive.getnames() == [
            "snapshot/library-artifacts.tsv",
            "snapshot/snapshot-manifest.json",
            "snapshot/tracks.tsv",
        ]


def test_snapshot_archive_is_reproducible_for_one_database_view(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    created_at = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    snapshots = SnapshotExporter(database, created_at=lambda: created_at)

    first = snapshots.create(tmp_path / "first", archive=True)
    second = snapshots.create(tmp_path / "second", archive=True)

    assert first.archive is not None and second.archive is not None
    assert first.archive.read_bytes() == second.archive.read_bytes()


def test_wheel_contains_snapshot_schema_for_resource_lookup(tmp_path: Path) -> None:
    distribution = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(distribution)],
        check=True,
        cwd=Path(__file__).parents[1],
        env={**os.environ, "UV_CACHE_DIR": str(tmp_path / "uv-cache")},
    )
    wheel = next(distribution.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(tmp_path / "installed")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; "
            "from dj_digger.catalog.database import Database; "
            "from dj_digger.exports.snapshot import SnapshotExporter; "
            "database = Database.open(Path('catalog.sqlite')); "
            "database.migrate(); "
            "SnapshotExporter(database).create(Path('snapshot'), archive=False)",
        ],
        check=False,
        cwd=tmp_path,
        env={"PYTHONPATH": str(tmp_path / "installed")},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
