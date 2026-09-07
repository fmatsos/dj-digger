from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import anyio
import pytest

from dj_digger.core.catalog.database import Database
from dj_digger.core.config import CurationConfig, WorkspaceConfig
from dj_digger.core.curation.agent import (
    CurationAgent,
    CurationGroundingError,
    CurationRequest,
    CurationTurnLimitError,
)
from dj_digger.core.curation.client import AssistantMessage, OpenAICompatibleClient


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


class _CompletionHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        body = json.dumps(
            {
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": None, "tool_calls": []},
                        "finish_reason": "stop",
                    }
                ]
            }
        ).encode()
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


@pytest.fixture
def completion_endpoint() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CompletionHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
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
    monkeypatch.setenv("OPENAI_API_KEY", "test-credential")
    config = _workspace(tmp_path / "catalog.sqlite", blocked_endpoint)
    agent = CurationAgent(config)
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


class _InjectedClient(OpenAICompatibleClient):
    def __init__(self, config: CurationConfig) -> None:
        super().__init__(config, "test-credential")
        self.calls = 0

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> AssistantMessage:
        self.calls += 1
        return AssistantMessage(role="assistant", content=None)


def test_explicit_client_seam_calls_overridden_complete(
    tmp_path: Path, completion_endpoint: str
) -> None:
    config = _workspace(tmp_path / "catalog.sqlite", completion_endpoint)
    client = _InjectedClient(config.curation)
    with pytest.raises(CurationGroundingError, match="must create"):
        anyio.run(
            CurationAgent(config, client).run,
            CurationRequest(prompt="Build a set"),
        )
    assert client.calls == 1


def test_client_worker_completion_stays_catalog_free(
    tmp_path: Path, completion_endpoint: str
) -> None:
    config = _workspace(tmp_path / "catalog.sqlite", completion_endpoint)
    request = {
        "protocol_version": 1,
        "config": asdict(config.curation),
        "messages": [{"role": "user", "content": "test"}],
        "tools": [],
    }
    script = """
import io
import json
import sys

import dj_digger.core.curation.client_worker as worker

before = set(sys.modules)
captured = io.BytesIO()
original = sys.stdout

class Capture:
    buffer = captured

sys.stdout = Capture()
try:
    code = worker.main()
finally:
    sys.stdout = original
after = set(sys.modules)
print(json.dumps({
    "code": code,
    "ok": json.loads(captured.getvalue())["ok"],
    "sqlite3": any(name == "sqlite3" or name.startswith("sqlite3.") for name in before | after),
    "catalog": any(
        name == "dj_digger.core.catalog" or name.startswith("dj_digger.core.catalog.")
        for name in before | after
    ),
}))
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path("src").resolve())
    environment["OPENAI_API_KEY"] = "test-credential"
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(request).encode(),
        capture_output=True,
        check=True,
        cwd=Path.cwd(),
        env=environment,
    )
    proof = json.loads(result.stdout)
    assert proof == {"code": 0, "ok": True, "sqlite3": False, "catalog": False}
