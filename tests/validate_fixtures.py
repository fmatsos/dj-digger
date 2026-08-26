"""Validate the curator's deterministic source-aware analysis fixtures."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
FIRST_PARTY_CONSUMER_FILES = (
    ROOT / "README.md",
    ROOT / "skills" / "electronic-dj-set-curator" / "SKILL.md",
    ROOT / "skills" / "electronic-dj-set-curator" / "references" / "compatibility-engine.md",
    ROOT / "skills" / "electronic-dj-set-curator" / "references" / "set-emission.md",
    ROOT / "skills" / "electronic-dj-set-curator" / "references" / "source-contracts.md",
)


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
    for path in FIRST_PARTY_CONSUMER_FILES:
        assert path.is_file(), f"missing first-party consumer: {path.relative_to(ROOT)}"
        text = path.read_text(encoding="utf-8")
        assert "djing-files.tsv" not in text, (
            f"deprecated inventory dependency: {path.relative_to(ROOT)}"
        )
        assert "music-files.tsv" not in text, (
            f"deprecated inventory dependency: {path.relative_to(ROOT)}"
        )

    tracks_path = FIXTURES / "tracks.tsv"
    assert tracks_path.is_file(), f"missing fixture: {tracks_path.relative_to(ROOT)}"
    with tracks_path.open(encoding="utf-8", newline="") as handle:
        tracks_reader = csv.DictReader(handle, delimiter="\t")
        tracks_columns = tracks_reader.fieldnames or []
        tracks_rows = list(tracks_reader)
    assert tracks_rows, "tracks.tsv must contain a deterministic first row"
    tracks_schema = json.loads(
        (ROOT / "schemas" / "tracks.schema.json").read_text(encoding="utf-8")
    )
    assert tracks_columns == tracks_schema["x-tabular"]["columns"]
    tracks_validator = Draft202012Validator(tracks_schema)
    for row in tracks_rows:
        tracks_validator.validate(_decode_tsv_row(row, tracks_schema))
    assert tracks_rows[0]["source_id"] == "djing"
    assert tracks_rows[0]["set_eligible"] == "true"
    assert tracks_rows[0]["path"] == "Techno/Fixture.flac"

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

    contract_paths = (
        ROOT / "skills" / "electronic-dj-set-curator" / "SKILL.md",
        ROOT / "skills" / "electronic-dj-set-curator" / "references" / "source-contracts.md",
    )
    contract_texts = []
    for path in contract_paths:
        assert path.is_file(), f"missing curator contract: {path.relative_to(ROOT)}"
        text = path.read_text(encoding="utf-8")
        contract_texts.append(text)
        for token in ("tracks.tsv", "set_eligible", "source_id", "exact path"):
            assert token in text, f"{path.relative_to(ROOT)} must mention {token}"
        assert "djing-files.tsv: existence" not in text

    source_contracts = contract_texts[-1]
    expected_precedence = [
        "1. `tracks.tsv` — current availability + `source_id` + `set_eligible` + exact path",
        "2. `dj-analysis.tsv` — track/global/window technical facts",
        "3. `dj-sections.jsonl` — structural facts",
        "4. `dj-analysis-run.json` — audit/staleness signal",
        "5. external context — classification/context only, never availability",
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
