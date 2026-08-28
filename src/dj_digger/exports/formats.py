"""Shared schema-driven writers for explicit export formats."""

import csv
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from dj_digger.exports.atomic import publish_atomic

FORMATS = {"json", "csv", "tsv"}


def fields_for_schema(schema: Mapping[str, Any]) -> tuple[str, ...]:
    tabular = schema.get("x-tabular")
    if isinstance(tabular, Mapping) and isinstance(tabular.get("columns"), list):
        return tuple(str(item) for item in tabular["columns"])
    properties = schema.get("properties", {})
    return tuple(str(item) for item in properties) if isinstance(properties, Mapping) else ()


def select_fields(available: Sequence[str], fields: str | None) -> tuple[str, ...] | None:
    if fields is None:
        return None
    if not fields.strip():
        raise ValueError("--fields must not be blank")
    selected = tuple(part.strip() for part in fields.split(","))
    if any(not part for part in selected):
        raise ValueError("--fields contains a blank field")
    if len(set(selected)) != len(selected):
        raise ValueError("--fields contains duplicate fields")
    unknown = [part for part in selected if part not in available]
    if unknown:
        raise ValueError(f"unknown field: {unknown[0]}")
    return selected


def projected(
    rows: Iterable[Mapping[str, Any]], fields: Sequence[str] | None
) -> list[dict[str, Any]]:
    return [
        dict(row) if fields is None else {field: row.get(field) for field in fields} for row in rows
    ]


def output_path(path: Path, fmt: str | None) -> Path:
    if fmt is None:
        return path
    if fmt not in FORMATS:
        raise ValueError(f"unknown export format: {fmt}")
    return path.with_suffix(f".{fmt}")


def write_rows(
    path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str], fmt: str
) -> None:
    def writer(target: Path) -> None:
        if fmt == "json":
            target.write_text(
                json.dumps(list(rows), ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            return
        delimiter = "," if fmt == "csv" else "\t"
        with target.open("w", encoding="utf-8", newline="") as handle:
            output = csv.DictWriter(
                handle, fieldnames=list(fields), delimiter=delimiter, lineterminator="\n"
            )
            output.writeheader()
            output.writerows({field: _cell(row.get(field)) for field in fields} for row in rows)

    publish_atomic(path, writer)


def write_object(path: Path, value: Mapping[str, Any], fields: Sequence[str], fmt: str) -> None:
    if fmt == "json":

        def writer(target: Path) -> None:
            target.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

        publish_atomic(path, writer)
        return
    write_rows(path, [value], fields, fmt)


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return str(value).lower()
    return value
