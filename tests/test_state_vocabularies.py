"""Domain states are named types, not repeated string literals."""

import pytest

from dj_digger.core.catalog.models import (
    AnalysisAttemptStatus,
    PresenceStatus,
    RunStatus,
    Track,
)
from dj_digger.core.curation.models import CurationStatus
from dj_digger.core.diagnostics import DiagnosticStatus
from dj_digger.core.jobs import JobStatus


@pytest.mark.parametrize(
    ("member", "value"),
    [
        (PresenceStatus.PRESENT, "present"),
        (PresenceStatus.MISSING, "missing"),
        (RunStatus.RUNNING, "running"),
        (RunStatus.SUCCEEDED, "succeeded"),
        (RunStatus.FAILED, "failed"),
        (AnalysisAttemptStatus.SUCCEEDED, "succeeded"),
        (AnalysisAttemptStatus.FAILED, "failed"),
        (DiagnosticStatus.SUCCEEDED, "succeeded"),
        (DiagnosticStatus.PARTIAL, "partial"),
        (DiagnosticStatus.FAILED, "failed"),
        (CurationStatus.DRAFT, "draft"),
        (CurationStatus.VALIDATED, "validated"),
        (JobStatus.STARTING, "starting"),
        (JobStatus.UNKNOWN, "unknown"),
    ],
)
def test_state_members_keep_their_persisted_wire_value(member: str, value: str) -> None:
    """Values are the catalog and JSON contract; the names are for the code."""
    assert member == value
    assert isinstance(member, str)


def test_states_bind_directly_as_sqlite_parameters() -> None:
    import sqlite3

    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE probe (state TEXT NOT NULL)")
    connection.execute("INSERT INTO probe (state) VALUES (?)", (PresenceStatus.PRESENT,))

    assert connection.execute("SELECT state FROM probe").fetchone() == ("present",)


def test_track_carries_a_typed_presence_state() -> None:
    track = Track(1, "library", "a/b.flac", "b.flac", "flac", 10, 20, PresenceStatus.PRESENT)

    assert track.presence_status is PresenceStatus.PRESENT
    assert track.presence_status == "present"


def test_separate_vocabularies_are_not_interchangeable() -> None:
    """A run state and a CLI diagnostic state share text but not meaning."""
    assert RunStatus.SUCCEEDED is not DiagnosticStatus.SUCCEEDED
    assert DiagnosticStatus.PARTIAL not in set(RunStatus)
