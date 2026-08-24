"""Canonical library-artifact export with optional legacy compatibility facets."""

import csv
import json
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import ArtifactRepository, SourceRepository
from dj_digger.exports.atomic import publish_atomic
from dj_digger.exports.legacy import LegacyExporter
from dj_digger.exports.tracks import PublishedFacet


class AuditExporter:
    def __init__(self, database: Database, *, artifacts_schema_path: Path | None = None) -> None:
        self._database = database
        packaged_schema = files("dj_digger").joinpath("schemas/library-artifacts.schema.json")
        schema_text = (
            artifacts_schema_path.read_text(encoding="utf-8")
            if artifacts_schema_path is not None
            else packaged_schema.read_text("utf-8")
            if packaged_schema.is_file()
            else (
                Path(__file__).resolve().parents[3] / "schemas/library-artifacts.schema.json"
            ).read_text(encoding="utf-8")
        )
        schema = json.loads(schema_text)
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(schema)
        self._columns = cast(list[str], schema["x-tabular"]["columns"])

    def export(self, destination: Path, legacy_compatibility: bool = True) -> list[PublishedFacet]:
        roots = SourceRepository(self._database).roots()
        rows = self._rows(roots)
        canonical = destination / "library-artifacts.tsv"

        def write(path: Path) -> None:
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=self._columns, delimiter="\t", lineterminator="\n"
                )
                writer.writeheader()
                for row in rows:
                    self._validator.validate(row)
                    writer.writerow({key: _serialize(row[key]) for key in self._columns})

        publish_atomic(canonical, write)
        facets = [PublishedFacet(canonical, len(rows))]
        return facets + (
            LegacyExporter(self._database).export(destination) if legacy_compatibility else []
        )

    def _rows(self, roots: dict[str, Path]) -> list[dict[str, Any]]:
        result = []
        for source, path, kind, size, mtime, first, last, missing in ArtifactRepository(
            self._database
        ).export_rows():
            result.append(
                {
                    "source_id": source,
                    "path": path,
                    "absolute_path": str(roots[str(source)] / str(path)),
                    "artifact_type": kind,
                    "size_bytes": size,
                    "mtime": datetime.fromtimestamp(int(mtime) // 1_000_000_000).isoformat(
                        timespec="seconds"
                    ),
                    "present": True,
                    "first_seen_at": first,
                    "last_seen_at": last,
                    "missing_since": missing,
                }
            )
        return result


def _serialize(value: Any) -> Any:
    return str(value).lower() if isinstance(value, bool) else ("" if value is None else value)
