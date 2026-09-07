from __future__ import annotations

import json
import subprocess
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anyio
import pytest

from dj_digger.catalog.database import Database
from dj_digger.config import CurationConfig, WorkspaceConfig
from dj_digger.curation.agent import CurationAgent, CurationRequest, CurationTurnLimitError
from dj_digger.curation.client import OpenAICompatibleClient


class _BlockingHandler(BaseHTTPRequestHandler):
    started = threading.Event()
    release = threading.Event()

    def do_POST(self) -> None:  # noqa: N802
        type(self).started.set()
        type(self).release.wait()
        body = json.dumps({"choices": []}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def blocked_endpoint() -> Iterator[str]:
    _BlockingHandler.started = threading.Event()
    _BlockingHandler.release = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _BlockingHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        _BlockingHandler.release.set()
        server.shutdown()
        thread.join()


def _workspace(path: Path, endpoint: str) -> WorkspaceConfig:
    with Database.open(path) as database:
        database.migrate()
        database.commit()
    return WorkspaceConfig(
        database=path,
        exports=path.parent / "exports",
        sources=(),
        curation=CurationConfig(
            base_url=endpoint,
            model="local-model",
            request_timeout_seconds=60.0,
            total_timeout_seconds=1.0,
            max_turns=1,
            max_output_tokens=1_000,
            max_output_tracks=10,
        ),
    )


def test_blocked_model_process_is_terminated_at_aggregate_deadline(
    tmp_path: Path, blocked_endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_CURATION_KEY", "test-credential")
    config = _workspace(tmp_path / "catalog.sqlite", blocked_endpoint)
    agent = CurationAgent(config, OpenAICompatibleClient(config.curation, "test-credential"))
    started = time.monotonic()
    with pytest.raises(CurationTurnLimitError):
        anyio.run(agent.run, CurationRequest(prompt="Build a set"))
    elapsed = time.monotonic() - started
    assert elapsed < 3.0
    assert _BlockingHandler.started.is_set()
    processes = subprocess.run(
        ["ps", "-eo", "args="], check=True, capture_output=True, text=True
    ).stdout
    assert "dj_digger.core.curation.client_worker" not in processes
