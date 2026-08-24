"""Offline evaluator for Acid Rave and adversarial recorded artifacts."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]
SCHEMA = json.loads((ROOT / "schemas/dj-set.schema.json").read_text(encoding="utf-8"))
STRATEGIES = {
    "LONG_BLEND",
    "STANDARD_BLEND",
    "LATE_BASS_HANDOFF",
    "SHORT_HANDOFF",
    "STRUCTURAL_SWAP",
    "BREAK_TRANSITION",
    "CUT_OR_ECHO",
}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def score(case_dir: Path, output_dir: Path) -> dict[str, bool]:
    tracks = _rows(case_dir / "tracks.tsv")
    eligible = {
        (r["source_id"], int(r["track_id"])): r for r in tracks if r["set_eligible"] == "true"
    }
    analysis = _rows(case_dir / "dj-analysis.tsv")
    bpms = {float(r["bpm"]) for r in analysis if r["bpm"]}
    analysis_by_path = {r["path"]: r for r in analysis}
    sections = [
        json.loads(line) for line in (case_dir / "dj-sections.jsonl").read_text().splitlines()
    ]
    sections_by_path = {r["path"]: set(r.get("sections", [])) for r in sections}
    run = json.loads((case_dir / "dj-analysis-run.json").read_text())
    payload = json.loads((output_dir / f"{case_dir.name}.set.json").read_text(encoding="utf-8"))
    result = {
        "schema": True,
        "membership": True,
        "paths": True,
        "constraints": True,
        "facts": True,
        "strategies": True,
        "uncertainty": True,
        "branches": True,
        "ambiguity": True,
        "artifacts": True,
    }
    try:
        Draft202012Validator(SCHEMA).validate(payload)
    except Exception:
        result["schema"] = False
    selected = payload.get("tracks", [])
    for track in selected:
        key = (track["source_id"], track["track_id"])
        if key not in eligible:
            result["membership"] = False
        elif track["path"] != eligible[key]["path"]:
            result["paths"] = False
    if any(
        t["target_bpm"] is not None and t["target_bpm"] not in bpms
        for t in payload.get("transitions", [])
    ):
        result["facts"] = False
    selected_by_path = {track["path"]: track for track in selected}
    for transition in payload.get("transitions", []):
        start = selected_by_path.get(transition["from_path"])
        end = selected_by_path.get(transition["to_path"])
        if not start or not end or transition["from_path"] == transition["to_path"]:
            result["facts"] = False
        if transition["outgoing_region"] not in sections_by_path.get(
            transition["from_path"], set()
        ):
            result["facts"] = False
        if transition["incoming_region"] not in sections_by_path.get(transition["to_path"], set()):
            result["facts"] = False
        target = analysis_by_path.get(transition["to_path"], {}).get("bpm")
        if target and transition["target_bpm"] != float(target):
            result["facts"] = False
    selected_paths = {track["path"] for track in selected}
    known_durations = [
        float(r["duration_seconds"])
        for r in analysis
        if r.get("duration_seconds") and r["path"] in selected_paths
    ]
    if known_durations:
        total_minutes = sum(known_durations) / 60
        target_minutes = payload["brief"]["target_duration_minutes"]
        if abs(total_minutes - target_minutes) > 1:
            result["constraints"] = False
    for alternative in payload.get("alternatives", []):
        key = (alternative["source_id"], alternative["track_id"])
        if key not in eligible or eligible[key]["path"] != alternative["path"]:
            result["membership"] = False
    if any(t["strategy"] not in STRATEGIES for t in payload.get("transitions", [])):
        result["strategies"] = False
    markdown = (output_dir / f"{case_dir.name}.md").read_text(encoding="utf-8").lower()
    playlist = [
        line
        for line in (output_dir / f"{case_dir.name}.m3u8").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    if playlist != [track["path"] for track in selected]:
        result["paths"] = False
    if "lossless" in payload["brief"]["hard"] and any(
        track["source_quality"] != "lossless" for track in selected
    ):
        result["constraints"] = False
    if (
        "mono-source" in payload["brief"]["hard"]
        and len({track["source_id"] for track in selected}) > 1
    ):
        result["constraints"] = False
    partial = (
        run.get("partial")
        or run.get("status") == "partial"
        or any(r.get("analysis_status") in {"partial", "missing"} for r in analysis)
    )
    if partial and "uncertain" not in markdown:
        result["uncertainty"] = False
    positions = re.findall(
        r"### position (\d+) candidates(.*?)(?=###|## improvisation|$)", markdown, re.S
    )
    selected_positions = {str(track["position"]) for track in selected}
    result["branches"] = (
        {number for number, _ in positions} == selected_positions
        and all(len(re.findall(r"(?m)^\s*\d+\.\s", body)) == 3 for _, body in positions)
        and "## improvisation branches" in markdown
    )
    for alternative in payload.get("alternatives", []):
        if (
            alternative["entry_from_path"] not in selected_by_path
            or alternative["rejoin_to_path"] not in selected_by_path
        ):
            result["paths"] = False
        if (
            alternative["entry_strategy"] not in STRATEGIES
            or alternative["exit_strategy"] not in STRATEGIES
        ):
            result["strategies"] = False
    if payload["validation"]["alternative_tracks"] != len(payload.get("alternatives", [])):
        result["constraints"] = False
    duplicate_paths = {r["path"] for r in tracks if sum(x["path"] == r["path"] for x in tracks) > 1}
    selected_paths = [track["path"] for track in selected]
    result["ambiguity"] = not (set(selected_paths) & duplicate_paths) and (
        not duplicate_paths or "ambiguous" in markdown or "refused" in markdown
    )
    names = {f.name for f in output_dir.iterdir()}
    result["artifacts"] = names == {
        f"{case_dir.name}.set.json",
        f"{case_dir.name}.m3u8",
        f"{case_dir.name}.md",
    }
    return result


def main() -> None:
    reports: list[dict[str, Any]] = []
    root = Path(__file__).parent / "cases"
    for case_dir in sorted(root.iterdir()):
        reports.append(
            {
                "case": case_dir.name,
                "baseline": score(case_dir, case_dir / "baseline"),
                "skill": score(case_dir, case_dir / "with-skill"),
            }
        )
    print(json.dumps(reports, sort_keys=True))


if __name__ == "__main__":
    main()
