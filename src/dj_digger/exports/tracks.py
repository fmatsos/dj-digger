"""Canonical track TSV export."""

import csv
import json
from dataclasses import dataclass
from datetime import datetime
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
from dj_digger.resources import read_text

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
    "integrated_lufs",
    "loudness_range_lu",
    "true_peak_dbtp",
    "short_term_lufs_p50",
    "short_term_lufs_p95",
    "peak_to_loudness_ratio_db",
    "required_gain_db",
    "available_gain_db",
    "gain_deficit_db",
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
        schema_text = (
            self._schema_path.read_text(encoding="utf-8")
            if self._schema_path is not None
            else read_text("schemas/tracks.schema.json")
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
            metadata = list(metadata_and_duplicate[:21])
            duplicate_group_id = metadata_and_duplicate[21]
            duplicate_best_quality = metadata_and_duplicate[22]
            mastering = list(metadata_and_duplicate[23:])
            if len(mastering) < 9:
                mastering.extend([None] * (9 - len(mastering)))
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
                *mastering,
            )
            result.append(dict(zip(ROW_FIELDS, projected, strict=True)))
        return result


def _serialize(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return value
