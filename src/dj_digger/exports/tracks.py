"""Canonical track TSV export."""

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import SourceRepository, TrackRepository
from dj_digger.exports.atomic import publish_atomic

ROW_FIELDS = (
    "source_id",
    "track_id",
    "path",
    "absolute_path",
    "filename",
    "extension",
    "size_bytes",
    "mtime",
    "set_eligible",
    "title",
    "artist",
    "album_artist",
    "album",
    "track_number",
    "disc_number",
    "genre",
    "date",
    "year",
    "composer",
    "comment",
    "tag_bpm",
    "tag_initial_key",
    "grouping",
    "duration_seconds",
    "sample_rate",
    "channels",
    "codec",
    "container",
    "bitrate",
    "lossless",
)


@dataclass(frozen=True)
class PublishedFacet:
    path: Path
    row_count: int


class TracksExporter:
    def __init__(self, database: Database, *, schema_path: Path | None = None) -> None:
        self._database = database
        self._schema_path = schema_path

    def export(self, destination: Path) -> PublishedFacet:
        packaged_schema = files("dj_digger").joinpath("schemas/tracks.schema.json")
        schema_text = (
            self._schema_path.read_text(encoding="utf-8")
            if self._schema_path is not None
            else packaged_schema.read_text("utf-8")
            if packaged_schema.is_file()
            else (Path(__file__).resolve().parents[3] / "schemas/tracks.schema.json").read_text(
                encoding="utf-8"
            )
        )
        schema = json.loads(schema_text)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        columns = cast(list[str], schema["x-tabular"]["columns"])
        roots = SourceRepository(self._database).roots()
        rows = self._rows(roots)

        def write(path: Path) -> None:
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=columns, delimiter="\t", lineterminator="\n"
                )
                writer.writeheader()
                for row in rows:
                    validator.validate(row)
                    writer.writerow({key: _serialize(row[key]) for key in columns})

        publish_atomic(destination, write)
        return PublishedFacet(path=destination, row_count=len(rows))

    def _rows(self, roots: dict[str, Path]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for values in TrackRepository(self._database).export_rows():
            track_id, source_id, path, filename, _extension, size, mtime, eligible, *metadata = (
                values
            )
            rel = str(path)
            if metadata[-1] is not None:
                metadata[-1] = bool(metadata[-1])
            mtime_seconds = int(mtime) // 1_000_000_000
            projected = (
                str(source_id),
                int(track_id),
                rel,
                str(roots[str(source_id)] / rel),
                str(filename),
                Path(rel).suffix.lower(),
                int(size),
                datetime.fromtimestamp(mtime_seconds).isoformat(timespec="seconds"),
                bool(eligible),
                *metadata,
            )
            result.append(dict(zip(ROW_FIELDS, projected, strict=True)))
        return result


def _serialize(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return value
