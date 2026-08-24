"""Validate the curator's deterministic source-aware analysis fixtures."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _read_analysis() -> tuple[list[str], list[dict[str, str]]]:
    path = FIXTURES / "dj-analysis.tsv"
    assert path.is_file(), f"missing fixture: {path.relative_to(ROOT)}"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return reader.fieldnames or [], list(reader)


def _decode_tsv_row(row: dict[str, str | None], schema: dict[str, object]) -> dict[str, object]:
    properties = schema["properties"]
    assert isinstance(properties, dict)
    decoded: dict[str, object] = {}
    for name, raw in row.items():
        raw = raw or ""
        definition = properties[name]
        assert isinstance(definition, dict)
        types = definition.get("type")
        nullable = isinstance(types, list) and "null" in types
        if raw == "" and nullable:
            decoded[name] = None
        elif types == "integer" or (isinstance(types, list) and "integer" in types):
            decoded[name] = int(raw)
        elif types == "number" or (isinstance(types, list) and "number" in types):
            decoded[name] = float(raw)
        elif types == "boolean" or (isinstance(types, list) and "boolean" in types):
            assert raw in {"true", "false"}
            decoded[name] = raw == "true"
        elif "const" in definition:
            decoded[name] = definition["const"]
        else:
            decoded[name] = raw
    return decoded


def main() -> None:
    columns, rows = _read_analysis()
    assert rows, "dj-analysis.tsv must contain a deterministic first row"
    first = rows[0]
    assert first["analysis_schema_version"] == "2"
    assert first["source_id"] == "djing"
    assert int(first["track_id"]) > 0

    analysis_schema = json.loads(
        (ROOT / "schemas" / "dj-analysis.schema.json").read_text(encoding="utf-8")
    )
    assert columns == analysis_schema["x-tabular"]["columns"]
    validator = Draft202012Validator(analysis_schema)
    for row in rows:
        validator.validate(_decode_tsv_row(row, analysis_schema))

    sections_path = FIXTURES / "dj-sections.jsonl"
    run_path = FIXTURES / "dj-analysis-run.json"
    assert sections_path.is_file(), f"missing fixture: {sections_path.relative_to(ROOT)}"
    assert run_path.is_file(), f"missing fixture: {run_path.relative_to(ROOT)}"
    sections = [json.loads(line) for line in sections_path.read_text(encoding="utf-8").splitlines()]
    run = json.loads(run_path.read_text(encoding="utf-8"))
    assert sections[0]["analysis_schema_version"] == 2
    assert sections[0]["source_id"] == "djing"
    assert sections[0]["track_id"] > 0
    assert run["analysis_schema_version"] == 2

    source_contracts = (
        ROOT / "skills" / "electronic-dj-set-curator" / "references" / "source-contracts.md"
    ).read_text(encoding="utf-8")
    expected_precedence = [
        "1. `djing-files.tsv` for V1A availability.",
        "2. `dj-analysis.tsv` and `dj-sections.jsonl` for source-aware analysis.",
        "3. `dj-analysis-run.json` for the analysis-run audit.",
    ]
    assert all(item in source_contracts for item in expected_precedence)

    for filename, value in (
        ("dj-sections.schema.json", sections[0]),
        ("dj-analysis-run.schema.json", run),
    ):
        schema = json.loads((ROOT / "schemas" / filename).read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


if __name__ == "__main__":
    main()
