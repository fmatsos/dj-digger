"""Every command payload is a well-formed diagnostic envelope."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dj_digger.cli.presenters.analyze import analyze_payload
from dj_digger.cli.presenters.duplicates import duplicate_mark_best_payload
from dj_digger.cli.presenters.export import export_payload
from dj_digger.cli.presenters.jobs import jobs_payload
from dj_digger.cli.presenters.metadata import metadata_payload
from dj_digger.cli.presenters.operations import operation_payload
from dj_digger.cli.presenters.refresh import refresh_payload
from dj_digger.cli.presenters.scan import scan_payload
from dj_digger.cli.presenters.snapshot import snapshot_payload
from dj_digger.core.analysis.pipeline import AnalysisRunResult
from dj_digger.core.application import (
    MetadataRunResult,
    ScanRunResult,
    ScanSourceResult,
)
from dj_digger.core.diagnostics import DiagnosticStatus
from dj_digger.core.duplicates.quality import QualityMarkResult
from dj_digger.core.exports.snapshot import SnapshotResult

PAYLOADS = {
    "analyze": analyze_payload(AnalysisRunResult(1, 2, 2, 0, 0, "succeeded")),
    "export": export_payload([Path("/tmp/tracks.tsv")]),
    "jobs": jobs_payload([]),
    "metadata": metadata_payload(MetadataRunResult(1, 0, 0)),
    "scan": scan_payload(ScanRunResult((ScanSourceResult("lib", True, 1, None),))),
    "snapshot": snapshot_payload(SnapshotResult(Path("/tmp/out"), None)),
    # Open payloads splat a result's fields and cannot be a closed TypedDict;
    # `open_diagnostic` is what still makes their envelope mandatory.
    "duplicates": duplicate_mark_best_payload(QualityMarkResult(status="succeeded", marked_best=0)),
    "refresh": refresh_payload({"event": "refresh", "status": "succeeded", "published": True}),
    "operation": operation_payload({"status": "succeeded", "checks": []}),
}


@pytest.mark.parametrize("event", sorted(PAYLOADS))
def test_every_payload_carries_its_event_and_a_known_status(event: str) -> None:
    payload = PAYLOADS[event]

    assert payload["event"] == event
    assert payload["status"] in set(DiagnosticStatus)


@pytest.mark.parametrize("event", sorted(PAYLOADS))
def test_every_payload_survives_the_machine_readable_encoding(event: str) -> None:
    encoded = json.dumps(PAYLOADS[event], ensure_ascii=False, sort_keys=True)

    decoded = json.loads(encoded)
    assert decoded["event"] == event
    assert isinstance(decoded["status"], str)


def test_a_payload_missing_its_status_is_a_type_error(tmp_path: Path) -> None:
    """The envelope is enforced statically, not only by this suite."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "from dj_digger.core.diagnostics import Diagnostic\n"
        "\n"
        "def broken() -> Diagnostic:\n"
        '    return {"event": "scan"}\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(probe)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert "status" in result.stdout


def test_an_open_payload_cannot_omit_its_envelope(tmp_path: Path) -> None:
    """`open_diagnostic` makes event and status positional, so neither can be lost."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "from dj_digger.core.diagnostics import open_diagnostic\n\nopen_diagnostic(groups=[])\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(probe)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert "event" in result.stdout
