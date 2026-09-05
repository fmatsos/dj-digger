import csv
import json
import os
from pathlib import Path

import pytest

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import ScanRunRepository, SourceRepository, TrackRepository

HASH = "a" * 64


def _payload() -> dict[str, object]:
    schema = json.loads(Path("schemas/dj-analysis.schema.json").read_text(encoding="utf-8"))
    projection_fields = {"source_id", "track_id", "path", "size_bytes", "mtime"}
    payload: dict[str, object] = {}
    for name in schema["required"]:
        if name in projection_fields:
            continue
        definition = schema["properties"][name]
        if "const" in definition:
            payload[name] = definition["const"]
        elif name == "analysis_status":
            payload[name] = "ok"
        elif name == "analyzer_version":
            payload[name] = "test"
        elif name == "config_hash":
            payload[name] = HASH
        elif "null" in definition.get("type", []):
            payload[name] = None
        elif definition.get("type") == "boolean":
            payload[name] = False
        elif definition.get("type") == "integer":
            payload[name] = 1
        elif definition.get("type") == "number":
            payload[name] = 1.0
        else:
            payload[name] = "test"
    for name in ("analysis_confidence", "duration_seconds", "lossless", "bpm", "beat_stability"):
        payload[name] = 1.0 if name != "lossless" else True
    return payload


def test_export_publishes_source_aware_validated_analysis_facets(tmp_path: Path) -> None:
    from dj_digger.analysis.exporters import AnalysisExporter

    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    with database.transaction():
        SourceRepository(database).upsert(
            "djing", tmp_path / "music", set_eligible=True, analyze=True, enabled=True
        )
    scan_id = ScanRunRepository(database).start("djing", scanner_version="test")
    with database.transaction():
        track = TrackRepository(database).insert(
            source_id="djing",
            relative_path="Techno/A.flac",
            filename="A.flac",
            extension=".flac",
            size_bytes=10,
            mtime_ns=20,
            scan_id=scan_id,
        )
    run = database.execute(
        """
        INSERT INTO analysis_runs (
            started_at, finished_at, status, eligible, analyzed, reused, failed,
            analysis_schema_version, analyzer_version, config_hash
        ) VALUES ('2026-01-01T00:00:00+00:00', '2026-01-01T00:01:00+00:00',
                  'succeeded', 1, 1, 0, 0, 2, 'test', ?)
        """,
        (HASH,),
    )
    database.execute(
        """
        INSERT INTO audio_analysis (
            track_id, analysis_run_id, analysis_schema_version, analyzer_version, config_hash,
            input_size_bytes, input_mtime_ns, analysis_status, analysis_confidence, payload_json,
            created_at
        ) VALUES (?, ?, 2, 'test', ?, 10, 20, 'succeeded', 1.0, ?, 'now')
        """,
        (track.id, run.lastrowid, HASH, json.dumps(_payload())),
    )
    database.commit()

    facets = AnalysisExporter(database).export(tmp_path / "export")

    analysis = tmp_path / "export" / "dj-analysis.tsv"
    rows = list(csv.DictReader(analysis.open(encoding="utf-8", newline=""), delimiter="\t"))
    assert [(row["source_id"], int(row["track_id"]), row["path"]) for row in rows] == [
        ("djing", track.id, "Techno/A.flac")
    ]
    assert (tmp_path / "export" / "dj-sections.jsonl").read_text(encoding="utf-8") == ""
    summary = json.loads((tmp_path / "export" / "dj-analysis-run.json").read_text())
    assert {"eligible", "analyzed", "reused", "failed"} <= summary.keys()
    assert "cached" not in summary and "pruned" not in summary
    assert [facet.path.name for facet in facets] == [
        "dj-analysis.tsv",
        "dj-sections.jsonl",
        "dj-analysis-run.json",
    ]


def test_export_rolls_back_all_previous_facets_when_second_publish_replace_fails(
    tmp_path: Path, monkeypatch
) -> None:
    from dj_digger.analysis.exporters import AnalysisExporter

    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    with database.transaction():
        SourceRepository(database).upsert(
            "djing", tmp_path / "music", set_eligible=True, analyze=True, enabled=True
        )
    scan_id = ScanRunRepository(database).start("djing", scanner_version="test")
    with database.transaction():
        track = TrackRepository(database).insert(
            source_id="djing",
            relative_path="A.flac",
            filename="A.flac",
            extension=".flac",
            size_bytes=10,
            mtime_ns=20,
            scan_id=scan_id,
        )
    run = database.execute(
        """
        INSERT INTO analysis_runs (
            started_at, finished_at, status, eligible, analyzed, reused, failed,
            analysis_schema_version, analyzer_version, config_hash
        ) VALUES ('s', 'f', 'succeeded', 1, 1, 0, 0, 2, 'test', ?)
        """,
        (HASH,),
    )
    database.execute(
        """
        INSERT INTO audio_analysis (
            track_id, analysis_run_id, analysis_schema_version, analyzer_version,
            config_hash, input_size_bytes, input_mtime_ns, analysis_status,
            analysis_confidence, payload_json, created_at
        ) VALUES (?, ?, 2, 'test', ?, 10, 20, 'succeeded', 1.0, ?, 'now')
        """,
        (track.id, run.lastrowid, HASH, json.dumps(_payload())),
    )
    database.commit()
    destination = tmp_path / "export"
    destination.mkdir()
    originals = {
        "dj-analysis.tsv": b"old-analysis",
        "dj-sections.jsonl": b"old-sections",
        "dj-analysis-run.json": b"old-run",
    }
    for name, content in originals.items():
        (destination / name).write_bytes(content)
    real_replace = os.replace
    staged_replacements = 0

    def replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        nonlocal staged_replacements
        if Path(source).parent.name.startswith(".analysis-publish-"):
            staged_replacements += 1
            if staged_replacements == 2:
                raise OSError("controlled publication failure")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", replace)
    with pytest.raises(OSError, match="controlled publication failure"):
        AnalysisExporter(database).export(destination)
    assert {name: (destination / name).read_bytes() for name in originals} == originals
    assert not list(destination.glob("*.bak"))
