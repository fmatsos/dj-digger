from pathlib import Path

from dj_digger.core.run_log import RunLogger


def test_run_logger_does_not_persist_private_error_details(tmp_path: Path) -> None:
    secret = "local-secret-sentinel /private/library/root/track.flac"
    RunLogger(tmp_path / "catalog.sqlite").write(
        {"event": "command", "status": "failed", "error": secret}
    )

    contents = (tmp_path / "logs" / "dj-digger.log").read_text(encoding="utf-8")
    assert secret not in contents
    assert "/private/library/root" not in contents
    assert "operation failed" in contents
