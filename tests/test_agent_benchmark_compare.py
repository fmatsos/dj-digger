# ruff: noqa: E501
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".docker-agent/scripts/benchmark-compare"


def report(values):
    return {"schema_version": "1.0", "sessions": [{"tokens": {"total": total, "input": total, "uncached_input": total - 1, "output": 2, "reasoning_output": 1}, "metrics": {"user_turns": 2, "discovery_calls": 1, "compactions": 0, "qa_invocations": 1}, "derived": {"repeated_discovery_count": 0, "full_qa_rate": 1, "qa_repair_cycles": 0, "post_review_rework_cycles": None, "subagent_token_share": 0.5}, "duration_seconds": 10} for total in values]}


def test_comparison_reports_median_p75_and_delta(tmp_path):
    baseline = tmp_path / "before.json"; after = tmp_path / "after.json"; output = tmp_path / "comparison.json"
    baseline.write_text(json.dumps(report([10, 20, 30])))
    after.write_text(json.dumps(report([5, 10, 15])))
    subprocess.run([str(SCRIPT), str(baseline), str(after), "--output", str(output)], check=True)
    result = json.loads(output.read_text())
    total = result["codex"]["tokens.total"]
    assert total["count"] == 3
    assert total["before"] == {"median": 20.0, "p75": 25.0}
    assert total["after"] == {"median": 10.0, "p75": 12.5}
    assert total["percent_delta"] == -50.0


def test_small_and_even_samples_use_linear_interpolation(tmp_path):
    baseline = tmp_path / "before.json"; after = tmp_path / "after.json"; output = tmp_path / "comparison.json"
    baseline.write_text(json.dumps(report([10, 30])))
    after.write_text(json.dumps(report([20, 40])))
    subprocess.run([str(SCRIPT), str(baseline), str(after), "--output", str(output)], check=True)
    total = json.loads(output.read_text())["codex"]["tokens.total"]
    assert total["before"]["p75"] == 25.0
    assert total["after"]["p75"] == 35.0


def test_missing_values_are_excluded_and_overhead_is_not_inferred(tmp_path):
    baseline = tmp_path / "before.json"; after = tmp_path / "after.json"; output = tmp_path / "comparison.json"
    before = report([10, 20]); after_data = report([5, 10]); after_data["sessions"][0]["derived"]["full_qa_rate"] = None
    baseline.write_text(json.dumps(before)); after.write_text(json.dumps(after_data))
    subprocess.run([str(SCRIPT), str(baseline), str(after), "--output", str(output)], check=True)
    result = json.loads(output.read_text())
    assert result["codex"]["full_qa_rate"]["count"] == 1
    assert result["docker_agent_overhead"] == {"token_usage": None, "budget_ceiling_tokens": 20000, "measurement_status": "unavailable"}
