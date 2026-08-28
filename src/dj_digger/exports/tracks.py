"""Canonical track TSV export."""

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from dj_digger.catalog.database import Database
from dj_digger.catalog.read_repositories import LibraryReadRepository
from dj_digger.catalog.repositories import SourceRepository
from dj_digger.exports.atomic import publish_atomic
from dj_digger.exports.formats import (
    fields_for_schema,
    output_path,
    projected,
    select_fields,
    write_rows,
)

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
    "duplicate_group_id",
    "duplicate_best_quality",
)


@dataclass(frozen=True)
class PublishedFacet:
    path: Path
    row_count: int


class TracksExporter:
    def __init__(self, database: Database, *, schema_path: Path | None = None) -> None:
        self._database = database
        self._schema_path = schema_path

    def export(
        self, destination: Path, *, format: str | None = None, fields: str | None = None
    ) -> PublishedFacet:
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
        columns = list(fields_for_schema(schema))
        selected = select_fields(columns, fields)
        roots = SourceRepository(self._database).roots()
        rows = self._rows(roots)

        for row in rows:
            validator.validate(row)
        target = output_path(destination, format)
        chosen = selected or tuple(columns)
        if format is None and fields is None:

            def write(path: Path) -> None:
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(
                        handle, fieldnames=columns, delimiter="\t", lineterminator="\n"
                    )
                    writer.writeheader()
                    writer.writerows({key: _serialize(row[key]) for key in columns} for row in rows)

            publish_atomic(target, write)
        else:
            write_rows(target, projected(rows, chosen), chosen, format or "tsv")

        return PublishedFacet(path=target, row_count=len(rows))

    def _rows(self, roots: dict[str, Path]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for values in LibraryReadRepository(self._database).export_rows():
            (
                track_id,
                source_id,
                path,
                filename,
                _extension,
                size,
                mtime,
                eligible,
                *metadata_and_duplicate,
            ) = values
            *metadata, duplicate_group_id, duplicate_best_quality = metadata_and_duplicate
            rel = str(path)
            if metadata[-1] is not None:
                metadata[-1] = bool(metadata[-1])
            if duplicate_best_quality is not None:
                duplicate_best_quality = bool(duplicate_best_quality)
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
                duplicate_group_id,
                duplicate_best_quality,
            )
            result.append(dict(zip(ROW_FIELDS, projected, strict=True)))
        return result


def _serialize(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return value
