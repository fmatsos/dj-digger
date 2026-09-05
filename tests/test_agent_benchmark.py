import json
import subprocess
from pathlib import Path

from jsonschema import validate

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".docker-agent/scripts/codex-session-benchmark"
FIXTURES = ROOT / "tests/fixtures/codex_sessions"


def run_collector(tmp_path: Path, *extra: str) -> dict:
    home = tmp_path / "codex"
    sessions = home / "sessions" / "2026" / "08" / "29"
    sessions.mkdir(parents=True)
    for fixture in FIXTURES.glob("*.jsonl"):
        (sessions / fixture.name).write_text(fixture.read_text())
    output = tmp_path / "report.json"
    subprocess.run(
        [
            str(SCRIPT),
            "--repo",
            "/repo/dj-digger",
            "--codex-home",
            str(home),
            "--limit",
            "2",
            "--output",
            str(output),
            *extra,
        ],
        check=True,
    )
    return json.loads(output.read_text())


def test_selects_latest_roots_groups_children_and_is_private(tmp_path):
    report = run_collector(tmp_path)
    assert report["summary"]["session_count"] == 2
    assert report["sessions"][0]["thread_count"] == 3
    assert report["sessions"][0]["session_key"].startswith("sha256:")
    serialized = json.dumps(report)
    assert "/repo/" not in serialized
    assert "session_id" not in serialized


def test_cumulative_usage_uses_last_snapshot_and_unknown_events_are_counted(tmp_path):
    report = run_collector(tmp_path, "--limit", "10")
    legacy = next(
        s for s in report["sessions"] if s["thread_count"] == 1 and s["tokens"]["total"] == 28
    )
    assert legacy["tokens"]["total"] == 28
    assert report["summary"]["unknown_event_count"] >= 2


def test_schema_and_csv_output(tmp_path):
    home = tmp_path / "codex"
    (home / "sessions").mkdir(parents=True)
    (home / "sessions" / "only.jsonl").write_text((FIXTURES / "legacy-root.jsonl").read_text())
    output = tmp_path / "report.json"
    csv_path = tmp_path / "report.csv"
    subprocess.run(
        [
            str(SCRIPT),
            "--repo",
            "/repo/dj-digger",
            "--codex-home",
            str(home),
            "--limit",
            "1",
            "--output",
            str(output),
            "--csv",
            str(csv_path),
        ],
        check=True,
    )
    report = json.loads(output.read_text())
    validate(report, json.loads((ROOT / ".docker-agent/schemas/benchmark.schema.json").read_text()))
    assert csv_path.read_text().startswith("session_key,")


def test_rejects_source_output(tmp_path):
    home = tmp_path / "codex"
    (home / "sessions").mkdir(parents=True)
    result = subprocess.run(
        [
            str(SCRIPT),
            "--repo",
            str(ROOT),
            "--codex-home",
            str(home),
            "--limit",
            "1",
            "--output",
            str(ROOT / "README.generated.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
