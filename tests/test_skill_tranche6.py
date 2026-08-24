from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SKILL = ROOT / "skills/electronic-dj-set-curator/SKILL.md"
EVAL = ROOT / "skills/electronic-dj-set-curator/evals"


def test_curator_skill_has_valid_frontmatter_and_stays_short() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert re.search(r"(?m)^name: [a-z0-9-]+$", text)
    assert re.search(r"(?m)^description: Use when .+$", text)
    assert text.splitlines()[3] == "---"
    assert len(text.splitlines()) < 500


def test_skill_declares_deterministic_input_order_and_artifacts() -> None:
    text = SKILL.read_text(encoding="utf-8")
    for token in (
        "tracks.tsv",
        "dj-analysis.tsv",
        "dj-sections.jsonl",
        "dj-analysis-run.json",
        "set_eligible=false",
        "3 branches",
        ".set.json",
        ".m3u8",
        "Markdown",
        "never availability",
        "ambiguous",
    ):
        assert token in text


def test_eval_harness_is_offline_and_contains_two_cases() -> None:
    harness = EVAL / "harness.py"
    assert harness.is_file()
    text = harness.read_text(encoding="utf-8")
    assert "Acid Rave" in text
    assert "adversarial" in text
    assert "subprocess" not in text
    for name in ("acid-rave", "adversarial"):
        assert (EVAL / f"{name}.json").is_file()
        case_dir = EVAL / "cases" / name
        assert (case_dir / "tracks.tsv").is_file()
        assert (case_dir / "dj-analysis.tsv").is_file()
        for output in ("baseline", "with-skill"):
            assert (case_dir / output / f"{name}.set.json").is_file()
            assert (case_dir / output / f"{name}.m3u8").is_file()
            assert (case_dir / output / f"{name}.md").is_file()


def test_eval_outputs_score_schema_paths_constraints_and_artifacts() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(EVAL / "harness.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    import json

    report = {row["case"]: row for row in json.loads(result.stdout)}
    assert all(report["acid-rave"]["skill"].values())
    assert report["acid-rave"]["baseline"]["facts"] is False
    assert report["acid-rave"]["baseline"]["branches"] is False
    assert report["adversarial"]["baseline"]["ambiguity"] is True
    assert report["adversarial"]["baseline"]["branches"] is False
    assert report["adversarial"]["baseline"]["uncertainty"] is False


def test_scorer_rejects_an_invented_skill_artifact(tmp_path: Path) -> None:
    import importlib.util
    import json
    import shutil
    import sys

    module_path = EVAL / "harness.py"
    spec = importlib.util.spec_from_file_location("tranche6_harness", module_path)
    assert spec and spec.loader
    harness = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = harness
    spec.loader.exec_module(harness)
    source = EVAL / "cases" / "acid-rave"
    output = tmp_path / "with-skill"
    shutil.copytree(source / "with-skill", output)
    payload = json.loads((output / "acid-rave.set.json").read_text())
    payload["transitions"][0]["target_bpm"] = 999
    (output / "acid-rave.set.json").write_text(json.dumps(payload))
    assert harness.score(source, output)["facts"] is False
