"""Self-describing, atomically published catalog snapshots."""

import gzip
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import SourceRepository
from dj_digger.exports.audit import AuditExporter
from dj_digger.exports.tracks import TracksExporter


@dataclass(frozen=True)
class SnapshotResult:
    directory: Path
    archive: Path | None


class SnapshotExporter:
    def __init__(
        self,
        database: Database,
        *,
        schema_path: Path | None = None,
        created_at: Callable[[], datetime] | None = None,
    ) -> None:
        self._database = database
        self._schema_path = schema_path
        self._created_at = created_at or (lambda: datetime.now(UTC))

    def create(self, output: Path, archive: bool) -> SnapshotResult:
        """Publish canonical facets and their validated integrity manifest."""
        if output.exists():
            raise FileExistsError(f"snapshot output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
        try:
            with self._database.read_transaction():
                facets = [
                    TracksExporter(self._database).export(staging / "tracks.tsv"),
                    *AuditExporter(self._database).export(staging),
                ]
                manifest = self._manifest(facets)
                self._validator().validate(manifest)
                (staging / "snapshot-manifest.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            os.replace(staging, output)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        archive_path = self._archive(output) if archive else None
        return SnapshotResult(directory=output, archive=archive_path)

    def _manifest(self, facets: list[Any]) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "created_at": self._created_at().isoformat(),
            "catalog_schema_version": 1,
            "tracks_export_schema_version": 2,
            "analysis_schema_version": 2,
            "sources": [
                {
                    "source_id": source_id,
                    "root_path": root_path,
                    "last_successful_scan_id": run_id,
                }
                for source_id, root_path, run_id in SourceRepository(self._database).all()
            ],
            "facets": [
                {
                    "name": facet.path.name,
                    "relative_path": facet.path.name,
                    "sha256": hashlib.sha256(facet.path.read_bytes()).hexdigest(),
                }
                for facet in sorted(facets, key=lambda facet: facet.path.name)
            ],
        }

    def _validator(self) -> Draft202012Validator:
        packaged_schema = files("dj_digger").joinpath("schemas/snapshot-manifest.schema.json")
        schema_text = (
            self._schema_path.read_text(encoding="utf-8")
            if self._schema_path is not None
            else packaged_schema.read_text("utf-8")
            if packaged_schema.is_file()
            else (
                Path(__file__).resolve().parents[3] / "schemas/snapshot-manifest.schema.json"
            ).read_text(encoding="utf-8")
        )
        schema = json.loads(schema_text)
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def _archive(self, directory: Path) -> Path:
        destination = directory.with_suffix(".tar.gz")
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            with (
                temporary.open("wb") as raw,
                gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed,
                tarfile.open(fileobj=compressed, mode="w") as archive,
            ):
                for path in sorted(directory.iterdir(), key=lambda item: item.name):
                    info = archive.gettarinfo(str(path), arcname=f"snapshot/{path.name}")
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    with path.open("rb") as handle:
                        archive.addfile(info, handle)
            os.replace(temporary, destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return destination
