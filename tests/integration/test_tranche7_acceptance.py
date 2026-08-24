"""Real acceptance gates for tranche 7 (no injected metadata or audio doubles)."""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from dj_digger.application import WorkspaceApplication
from dj_digger.config import ExportConfig, LibrarySourceConfig, WorkspaceConfig

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "scripts" / "acceptance_library_pilot.py"


def _typed_row(row: dict[str, str], schema: dict[str, object]) -> dict[str, object]:
    properties = schema["properties"]
    assert isinstance(properties, dict)
    typed: dict[str, object] = {}
    for key, value in row.items():
        definition = properties.get(key, {})
        kind = definition.get("type") if isinstance(definition, dict) else None
        kinds = {kind} if isinstance(kind, str) else set(kind or ())
        if value == "":
            typed[key] = None
        elif isinstance(definition, dict) and "const" in definition:
            constant = definition["const"]
            if isinstance(constant, bool):
                typed[key] = value.lower() == "true"
            else:
                typed[key] = type(constant)(value)
        elif "integer" in kinds:
            typed[key] = int(value)
        elif "number" in kinds:
            typed[key] = float(value)
        elif "boolean" in kinds:
            typed[key] = value.lower() == "true"
        else:
            typed[key] = value
    return typed


COPY_SET = ROOT / "references" / "copy-set.sh"


def _real_workspace(tmp_path: Path, source: Path, *, legacy: bool = False) -> WorkspaceConfig:
    return WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        export=ExportConfig(legacy),
        sources=(LibrarySourceConfig("music", source, True, True, True),),
    )


@pytest.mark.skipif(
    any(shutil.which(binary) is None for binary in ("exiftool", "ffmpeg", "ffprobe"))
    or importlib.util.find_spec("essentia") is None,
    reason="real V1A acceptance requires ExifTool, FFmpeg/ffprobe and essentia",
)
def test_real_v1a_composition_metadata_analysis_reuse_export_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "library"
    source.mkdir()
    audio = source / "real.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(audio)],
        check=True,
    )
    application = WorkspaceApplication(_real_workspace(tmp_path, source))
    assert application.scan()[0].succeeded
    metadata = application.metadata()
    assert metadata.extracted == 1
    first = application.analyze()
    second = application.analyze(force=True)
    assert first.analyzed == 1 and first.failed == 0
    assert second.analyzed == 0 and second.reused == 1
    published = application.export("all")
    assert {Path(path).name for path in published} >= {
        "tracks.tsv",
        "dj-analysis.tsv",
        "dj-sections.jsonl",
        "dj-analysis-run.json",
    }
    snapshot = application.snapshot(tmp_path / "snapshot", archive=True)
    manifest = json.loads((snapshot.directory / "snapshot-manifest.json").read_text())
    Draft202012Validator(
        json.loads((ROOT / "schemas/snapshot-manifest.schema.json").read_text())
    ).validate(manifest)
    # Validate every canonical analysis facet, not only the snapshot wrapper.
    analysis_schema = json.loads((ROOT / "schemas/dj-analysis.schema.json").read_text())
    sections_schema = json.loads((ROOT / "schemas/dj-sections.schema.json").read_text())
    run_schema = json.loads((ROOT / "schemas/dj-analysis-run.schema.json").read_text())
    analysis_rows = list(
        csv.DictReader((application.config.exports / "dj-analysis.tsv").open(), delimiter="\t")
    )
    assert analysis_rows
    for row in analysis_rows:
        Draft202012Validator(analysis_schema).validate(_typed_row(row, analysis_schema))
    for line in (application.config.exports / "dj-sections.jsonl").read_text().splitlines():
        Draft202012Validator(sections_schema).validate(json.loads(line))
    Draft202012Validator(run_schema).validate(
        json.loads((application.config.exports / "dj-analysis-run.json").read_text())
    )


def test_library_pilot_is_manual_bounded_and_skips_without_environment(tmp_path: Path) -> None:
    assert PILOT.is_file()
    result = subprocess.run(["python3", str(PILOT)], text=True, capture_output=True)
    assert result.returncode in {0, 1}
    assert json.loads(result.stdout)["status"] == "skipped"

    library = tmp_path / "library"
    library.mkdir()
    for index in range(12):
        (library / f"{index:02d}.wav").write_bytes(b"fixture")
    result = subprocess.run(
        ["python3", str(PILOT)],
        env=os.environ | {"DJ_DIGGER_LIBRARY_ROOT": str(library)},
        text=True,
        capture_output=True,
    )
    assert result.returncode in {0, 1}
    report = json.loads(result.stdout)
    assert report["status"] in {"accepted", "blocked", "skipped"}
    assert report["bounded_tracks"] <= 10
    assert isinstance(report.get("analysis_error_stages", {}), dict)
    assert isinstance(report.get("cli_error_categories", {}), dict)
    if report["status"] != "skipped":
        assert isinstance(report.get("analysis_runs"), int)
        assert isinstance(report.get("analysis_attempts"), int)
    assert "library" not in result.stdout


def test_validated_curator_m3u8_is_consumed_by_copy_set(tmp_path: Path) -> None:
    case = ROOT / "skills/electronic-dj-set-curator/evals/cases/acid-rave/with-skill"
    playlist = case / "acid-rave.m3u8"
    library = tmp_path / "library"
    output = tmp_path / "copied"
    paths = [
        line for line in playlist.read_text().splitlines() if line and not line.startswith("#")
    ]
    for relative in paths:
        target = library / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative.encode())
    source_snapshot = {
        relative: ((library / relative).read_bytes(), (library / relative).stat().st_mtime_ns)
        for relative in paths
    }
    tools = tmp_path / "tools"
    tools.mkdir()
    fake_chown = tools / "chown"
    fake_chown.write_text("#!/bin/sh\nexit 0\n")
    fake_chown.chmod(0o755)
    subprocess.run(
        [
            "bash",
            str(COPY_SET),
            "--library",
            str(library),
            "--output",
            str(output),
            "--playlist",
            str(playlist),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ | {"PATH": f"{tools}:{os.environ['PATH']}"},
    )
    copied = [
        line
        for line in (output / playlist.name).read_text().splitlines()
        if line and not line.startswith("#")
    ]
    assert len(copied) == len(paths)
    assert all((output / path).is_file() for path in copied)
    assert all((library / relative).read_bytes() == relative.encode() for relative in paths)
    assert all(
        ((library / relative).read_bytes(), (library / relative).stat().st_mtime_ns)
        == source_snapshot[relative]
        for relative in paths
    )


def test_reconstructed_curator_consumes_canonical_facets_and_emits_three_valid_outputs() -> None:
    harness_path = ROOT / "skills/electronic-dj-set-curator/evals/harness.py"
    namespace: dict[str, object] = {"__file__": str(harness_path)}
    exec(harness_path.read_text(encoding="utf-8"), namespace)
    case = ROOT / "skills/electronic-dj-set-curator/evals/cases/acid-rave"
    result = namespace["score"](case, case / "with-skill")  # type: ignore[index,operator]
    assert all(result.values())
    assert {path.name for path in (case / "with-skill").iterdir()} == {
        "acid-rave.set.json",
        "acid-rave.m3u8",
        "acid-rave.md",
    }


@pytest.mark.skipif(
    any(shutil.which(binary) is None for binary in ("exiftool", "ffmpeg", "ffprobe"))
    or importlib.util.find_spec("essentia") is None,
    reason="real V1B acceptance requires ExifTool, FFmpeg/ffprobe and essentia",
)
def test_v1b_refresh_emits_schema_valid_facts_only_set(tmp_path: Path) -> None:
    harness_path = ROOT / "skills/electronic-dj-set-curator/evals/harness.py"
    namespace: dict[str, object] = {"__file__": str(harness_path)}
    exec(harness_path.read_text(encoding="utf-8"), namespace)
    source = tmp_path / "library"
    source.mkdir()
    audio = source / "synth.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(audio)],
        check=True,
    )
    config = _real_workspace(tmp_path, source, legacy=False)
    refresh = WorkspaceApplication(config).refresh()
    assert refresh["published"] is True
    assert all(
        (config.exports / name).is_file()
        for name in ("tracks.tsv", "dj-analysis.tsv", "dj-sections.jsonl", "dj-analysis-run.json")
    )
    assert not (config.exports / "music-files.tsv").exists()
    assert not (config.exports / "djing-files.tsv").exists()
    output = tmp_path / "output"
    namespace["emit_facts_only"](config.exports, output, "dynamic")  # type: ignore[index]
    assert {path.name for path in output.iterdir()} == {
        "dynamic.set.json",
        "dynamic.m3u8",
        "dynamic.md",
    }
    schema = json.loads((ROOT / "schemas/dj-set.schema.json").read_text(encoding="utf-8"))
    payload = json.loads((output / "dynamic.set.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
    tracks = list(csv.DictReader((config.exports / "tracks.tsv").open(), delimiter="\t"))
    membership = {(row["source_id"], row["track_id"], row["path"]) for row in tracks}
    assert all(
        (str(track["source_id"]), str(track["track_id"]), str(track["path"])) in membership
        for track in payload["tracks"]
    )
    playlist = [
        line
        for line in (output / "dynamic.m3u8").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    assert playlist == [track["path"] for track in payload["tracks"]]
    assert (output / "dynamic.md").read_text(encoding="utf-8").strip()
