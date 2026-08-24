from pathlib import Path
from runpy import run_path

_error_category = run_path(
    str(Path(__file__).parents[1] / "scripts" / "acceptance_library_pilot.py")
)["_error_category"]


def test_library_pilot_forces_second_analysis_for_reuse() -> None:
    source = Path(__file__).parents[1] / "scripts" / "acceptance_library_pilot.py"
    text = source.read_text(encoding="utf-8")
    assert 'second_exit, second = run_cli("analyze", "--limit", "10", "--force")' in text


def test_error_category_redacts_pre_persistence_failures() -> None:
    cases = {
        "nan value": "non_finite_analysis",
        "JSON is not serializable": "serialization",
        "analysis section must be object": "section_persistence",
        "FOREIGN KEY constraint failed": "constraint",
        "expected mapping object": "empty_payload/type_error",
    }
    for error, category in cases.items():
        assert _error_category({"status": "failed", "error": error}) == category
    assert _error_category({"status": "failed", "error": "/private/library/file.wav"}) == "unknown"
