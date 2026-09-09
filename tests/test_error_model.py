"""The persisted failure class is derived from the exception type, not its text."""

from pathlib import Path

import pytest

from dj_digger.core.curation.client import (
    CurationAuthenticationError,
    CurationResponseError,
    CurationTimeoutError,
    CurationTransportError,
)
from dj_digger.core.errors import (
    CoreError,
    DependencyError,
    DependencyTimeoutError,
    IntegrityError,
    InvalidInputError,
    ResourceNotFoundError,
    StateConflictError,
)
from dj_digger.core.run_log import RunLogger, sanitize_error


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (InvalidInputError("limit must be positive"), "invalid input"),
        (ResourceNotFoundError("unknown source"), "unavailable"),
        (StateConflictError("already validated"), "state conflict"),
        (DependencyError("ffmpeg is missing"), "dependency unavailable"),
        (DependencyTimeoutError("ffmpeg took too long"), "timeout"),
        (IntegrityError("checksum mismatch"), "integrity"),
        (CurationAuthenticationError("no credential"), "authentication"),
        (CurationTimeoutError("model took too long"), "timeout"),
        (CurationTransportError("endpoint refused"), "unavailable"),
        (CurationResponseError("malformed payload"), "invalid response"),
        (RuntimeError("some internal bug"), "operation failed"),
    ],
)
def test_failure_class_is_derived_from_the_exception_type(error: Exception, expected: str) -> None:
    assert sanitize_error(error) == expected


def test_a_reworded_message_does_not_change_the_persisted_failure_class() -> None:
    """Classification must survive message edits, unlike substring matching."""
    assert sanitize_error(DependencyTimeoutError("exceeded its budget")) == "timeout"
    assert sanitize_error(InvalidInputError("workers must be greater than zero")) == "invalid input"


def test_unexpected_exception_text_never_reaches_the_persisted_log(tmp_path: Path) -> None:
    secret = "local-secret-sentinel /private/library/root/track.flac"
    RunLogger(tmp_path / "catalog.sqlite").write(
        {"event": "command", "status": "failed", "error": secret}
    )

    contents = (tmp_path / "logs" / "dj-digger.log").read_text(encoding="utf-8")
    assert secret not in contents
    assert "operation failed" in contents


def test_expected_domain_errors_stay_catchable_as_their_builtin_kind() -> None:
    """Callers written against ValueError/RuntimeError keep working."""
    assert issubclass(InvalidInputError, ValueError)
    assert issubclass(StateConflictError, RuntimeError)
    assert issubclass(ResourceNotFoundError, ValueError)
    for error_type in (
        InvalidInputError,
        ResourceNotFoundError,
        StateConflictError,
        DependencyError,
        IntegrityError,
    ):
        assert issubclass(error_type, CoreError)


def test_curation_errors_participate_in_the_core_hierarchy() -> None:
    for error_type in (
        CurationAuthenticationError,
        CurationTimeoutError,
        CurationTransportError,
        CurationResponseError,
    ):
        assert issubclass(error_type, CoreError)


def test_path_scrubbing_leaves_configured_endpoints_readable(tmp_path: Path) -> None:
    """Scrubbing private paths must not mangle the URLs a diagnostic reports."""
    RunLogger(tmp_path / "catalog.sqlite").write(
        {
            "event": "curation",
            "status": "failed",
            "endpoint": "https://api.example.test/v1",
            "library": "/private/library/root/track.flac",
        }
    )

    contents = (tmp_path / "logs" / "dj-digger.log").read_text(encoding="utf-8")
    assert "https://api.example.test/v1" in contents
    assert "/private/library/root" not in contents


def test_an_absent_error_is_not_reported_as_a_failure_class(tmp_path: Path) -> None:
    """A successful run carrying `error: null` must not read as a failure."""
    RunLogger(tmp_path / "catalog.sqlite").write(
        {"event": "scan", "status": "succeeded", "scans": [{"source_id": "a", "error": None}]}
    )

    contents = (tmp_path / "logs" / "dj-digger.log").read_text(encoding="utf-8")
    assert '"error": null' in contents
    assert "operation failed" not in contents
