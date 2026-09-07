from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dj_digger.cli import app
from dj_digger.core.catalog.database import Database


class _Endpoint(BaseHTTPRequestHandler):
    response: bytes = b""

    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(type(self).response)))
        self.end_headers()
        self.wfile.write(type(self).response)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def endpoint() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Endpoint)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        thread.join()


def _workspace(tmp_path: Path, endpoint: str) -> tuple[Path, Path]:
    database_path = tmp_path / "catalog.sqlite"
    with Database.open(database_path) as database:
        database.migrate()
        database.execute(
            "INSERT INTO library_sources VALUES (?, ?, 1, 1, 1, ?, ?, NULL)",
            ("public-source", "/private/library/root", "now", "now"),
        )
        database.execute(
            "INSERT INTO scan_runs (id, source_id, started_at, status, scanner_version) "
            "VALUES (1, 'public-source', 'now', 'succeeded', 'test')"
        )
        database.execute(
            "INSERT INTO tracks (id, source_id, relative_path, filename, extension, size_bytes, "
            "mtime_ns, presence_status, discovered_at, last_seen_at, created_scan_id, "
            "last_seen_scan_id) VALUES (1, 'public-source', 'safe.flac', 'safe.flac', '.flac', "
            "1, 1, 'present', 'now', 'now', 1, 1)"
        )
        database.execute(
            "INSERT INTO tracks (id, source_id, relative_path, filename, extension, size_bytes, "
            "mtime_ns, presence_status, discovered_at, last_seen_at, created_scan_id, "
            "last_seen_scan_id) VALUES (2, 'public-source', 'second.flac', 'second.flac', "
            "'.flac', 1, 1, 'present', 'now', 'now', 1, 1)"
        )
        database.commit()
    config = tmp_path / "config.toml"
    config.write_text(
        f'''[workspace]\ndatabase = "{database_path}"\nexports = "{tmp_path / "exports"}"\n\n'''
        "[library]\nsources = []\n\n"
        f'''[curation]\nbase_url = "{endpoint}"\nmodel = "local-test"\n'''
        """api_key_env = "TEST_CURATION_KEY"\nrequest_timeout_seconds = 1\n"""
        """total_timeout_seconds = 2\nmax_turns = 2\n"""
    )
    return config, database_path


def _completion(*, track_id: int = 1) -> bytes:
    arguments: dict[str, Any] = {
        "name": "Model name",
        "kind": "set",
        "user_prompt": "rewritten",
        "report_markdown": "# Report\nGrounded selection.",
        "tracks": [{"source_id": "public-source", "track_id": track_id}],
    }
    return json.dumps(
        {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "create",
                                "type": "function",
                                "function": {
                                    "name": "create_curation",
                                    "arguments": json.dumps(arguments),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    ).encode()


def test_create_show_list_and_explicit_validate(
    tmp_path: Path, endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _workspace(tmp_path, endpoint)
    monkeypatch.setenv("TEST_CURATION_KEY", "local-secret")
    _Endpoint.response = _completion()
    runner = CliRunner()

    created = runner.invoke(
        app,
        [
            "curation",
            "create",
            "Build a compact progression",
            "--kind",
            "playlist",
            "--name",
            "Reviewed name",
            "--config",
            str(config),
            "--json",
        ],
    )
    assert created.exit_code == 0, created.output
    payload = json.loads(created.stdout)
    assert payload["status"] == "draft"
    assert payload["kind"] == "playlist"
    assert payload["name"] == "Reviewed name"
    creation_id = payload["id"]
    with Database.open_read_only(database_path) as database:
        assert database.scalar("SELECT status FROM curation_creations") == "draft"
        assert database.scalar("SELECT count(*) FROM curation_creation_tracks") == 1

    shown = runner.invoke(app, ["curation", "show", creation_id, "--config", str(config), "--json"])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["report_markdown"].startswith("# Report")
    assert "/private/library/root" not in shown.output

    listed = runner.invoke(
        app, ["curation", "list", "--status", "draft", "--config", str(config), "--json"]
    )
    assert listed.exit_code == 0
    assert [item["id"] for item in json.loads(listed.stdout)["curations"]] == [creation_id]

    validated = runner.invoke(
        app, ["curation", "validate", creation_id, "--config", str(config), "--json"]
    )
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["status"] == "validated"

    conflict = runner.invoke(app, ["curation", "validate", creation_id, "--config", str(config)])
    assert conflict.exit_code == 1
    assert "state conflict" in conflict.stderr


@pytest.mark.parametrize(
    "response,credential,error",
    [
        (b"not json", "yes", "invalid response"),
        (_completion(track_id=999), "yes", "stale"),
        (_completion(), None, "authentication"),
    ],
)
def test_create_failures_leave_no_partial_rows(
    tmp_path: Path,
    endpoint: str,
    monkeypatch: pytest.MonkeyPatch,
    response: bytes,
    credential: str | None,
    error: str,
) -> None:
    config, database_path = _workspace(tmp_path, endpoint)
    if credential is not None:
        monkeypatch.setenv("TEST_CURATION_KEY", credential)
    _Endpoint.response = response

    result = CliRunner().invoke(
        app, ["curation", "create", "Build safely", "--config", str(config)]
    )

    assert result.exit_code == 1
    assert error in result.stderr.lower()
    assert "local-secret" not in result.output
    assert "/private/library/root" not in result.output
    log = (database_path.parent / "logs" / "dj-digger.log").read_text(encoding="utf-8")
    assert '"event": "curation"' in log
    assert '"status": "failed"' in log
    assert error in log.lower()
    with Database.open_read_only(database_path) as database:
        assert database.scalar("SELECT count(*) FROM curation_creations") == 0
        assert database.scalar("SELECT count(*) FROM curation_creation_tracks") == 0


def test_create_rejects_track_count_before_persisting_draft(
    tmp_path: Path, endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _workspace(tmp_path, endpoint)
    monkeypatch.setenv("TEST_CURATION_KEY", "local-credential")
    response = json.loads(_completion())
    arguments = response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
    creation = json.loads(arguments)
    creation["tracks"].append({"source_id": "public-source", "track_id": 2})
    response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = json.dumps(
        creation
    )
    _Endpoint.response = json.dumps(response).encode()

    result = CliRunner().invoke(
        app,
        [
            "curation",
            "create",
            "Build one selection",
            "--max-tracks",
            "1",
            "--config",
            str(config),
        ],
    )

    assert result.exit_code == 1
    with Database.open_read_only(database_path) as database:
        assert database.scalar("SELECT count(*) FROM curation_creations") == 0
        assert database.scalar("SELECT count(*) FROM curation_creation_tracks") == 0
