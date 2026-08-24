"""Contract checks for the tranche-8 requalification record."""

from __future__ import annotations

import re
from pathlib import Path

DOC = Path(__file__).parents[1] / "docs/acceptance/implementation-requalification.md"


def _status_table(text: str) -> dict[tuple[str, int], str]:
    rows = re.findall(r"\| (Catalogue|Analyse|Curateur|Intégration) \| (\d+) \| (\w+) \|", text)
    return {(domain, int(task)): status for domain, task, status in rows}


def test_requalification_matrix_and_local_library_gate_are_explicit() -> None:
    text = DOC.read_text(encoding="utf-8")
    statuses = _status_table(text)
    for task in (1, 5, 7, 9):
        assert statuses["Catalogue", task] == "COMPLETE"
    for task in range(11, 18):
        assert statuses["Analyse", task] == "COMPLETE"
    for task in range(18, 24):
        assert statuses["Curateur", task] == "COMPLETE"
    for task in (25, 27, 28, 29, 30):
        assert statuses["Intégration", task] == "COMPLETE"
    assert "DJ_DIGGER_LIBRARY_ROOT" in text
    assert '"status": "accepted"' in text
    assert '"bounded_tracks": 9' in text
    assert '"second_reused": true' in text
    assert '"source_unchanged": true' in text
    assert "skipped" not in text.lower()
    assert "Essentia absent" not in text
    assert "sans prétention de parité moteur absent" in text
    assert "CIFS" not in text
