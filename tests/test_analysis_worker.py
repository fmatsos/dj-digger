import json
import os
import signal
import subprocess
from io import BytesIO
from pathlib import Path

import pytest

from dj_digger.analysis.extractor import AnalysisExtractionError, AnalysisExtractionResult
from dj_digger.analysis.worker import PROTOCOL_VERSION, execute_request
from dj_digger.analysis.worker_client import IsolatedAnalysisExtractor
from dj_digger.catalog.models import Track
from dj_digger.config import DspConfig


def _request(tmp_path: Path) -> dict[str, object]:
    dsp = DspConfig.canonical()
    return {
        "protocol_version": PROTOCOL_VERSION,
        "path": str(tmp_path / "track.flac"),
        "track": {"source_id": "library", "track_id": 7, "relative_path": "track.flac"},
        "dsp": {
            "version": dsp.version,
            "sample_rate": dsp.sample_rate,
            "channels": dsp.channels,
            "fft_window_size": dsp.fft_window_size,
            "fft_hop_size": dsp.fft_hop_size,
            "bands": {key: list(value) for key, value in dsp.bands.items()},
            "segmentation_min_seconds": dsp.segmentation_min_seconds,
            "segmentation_max_seconds": dsp.segmentation_max_seconds,
            "semantic_min_confidence": dsp.semantic_min_confidence,
        },
    }


def test_worker_returns_versioned_success_without_changing_payloads(tmp_path: Path) -> None:
    expected = AnalysisExtractionResult(
        {"path": "track.flac", "facts": [1, 2]},
        {"sections": [{"index": 0}]},
        0.75,
        "succeeded",
    )

    class Extractor:
        def extract(self, *args: object, **kwargs: object) -> AnalysisExtractionResult:
            return expected

    response = execute_request(_request(tmp_path), extractor_factory=lambda dsp: Extractor())

    assert response == {
        "protocol_version": PROTOCOL_VERSION,
        "status": "succeeded",
        "result": {
            "payload": expected.payload,
            "sections": expected.sections,
            "confidence": 0.75,
            "status": "succeeded",
        },
    }


def test_worker_preserves_structured_python_failure_stage_and_message(tmp_path: Path) -> None:
    class Extractor:
        def extract(self, *args: object, **kwargs: object) -> AnalysisExtractionResult:
            raise AnalysisExtractionError("spectrum", "spectrum stage failed")

    response = execute_request(_request(tmp_path), extractor_factory=lambda dsp: Extractor())

    assert response["status"] == "failed"
    assert response["error"] == {"stage": "spectrum", "message": "spectrum stage failed"}


@pytest.mark.parametrize("status", ["partial", "failed"])
def test_worker_rejects_non_success_extraction_results(
    tmp_path: Path, status: str
) -> None:
    class Extractor:
        def extract(self, *args: object, **kwargs: object) -> AnalysisExtractionResult:
            return AnalysisExtractionResult({}, {"sections": []}, None, status)  # type: ignore[arg-type]

    response = execute_request(_request(tmp_path), extractor_factory=lambda dsp: Extractor())

    assert response == {
        "protocol_version": PROTOCOL_VERSION,
        "status": "failed",
        "error": {
            "stage": "aggregation",
            "message": f"worker extraction returned non-success status: {status}",
        },
    }


class _FakeProcess:
    def __init__(
        self,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        timeout: bool = False,
        pid: int = 4321,
    ) -> None:
        self.stdin = BytesIO()
        self.stdout = BytesIO(stdout)
        self.stderr = BytesIO(stderr)
        self.returncode = returncode
        self.timeout = timeout
        self.pid = pid
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        if self.timeout:
            self.timeout = False
            raise subprocess.TimeoutExpired(["python"], timeout or 0)
        return self.returncode

    def kill(self) -> None:
        self.killed = True


def _track() -> Track:
    return Track(7, "library", "track.flac", "track.flac", ".flac", 10, 20, "present")


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, process: _FakeProcess):
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    return IsolatedAnalysisExtractor(
        {"library": tmp_path}, DspConfig.canonical(), executable="python"
    )


def test_parent_validates_success_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "protocol_version": PROTOCOL_VERSION,
        "status": "succeeded",
        "result": {
            "payload": {"path": "track.flac"},
            "sections": {"sections": []},
            "confidence": None,
            "status": "succeeded",
        },
    }
    client = _client(
        tmp_path,
        monkeypatch,
        _FakeProcess(stdout=json.dumps(response).encode()),
    )

    result = client.extract(_track(), timeout=2)

    assert result.payload == {"path": "track.flac"}
    assert result.sections == {"sections": []}


@pytest.mark.parametrize("status", ["partial", "failed"])
def test_parent_rejects_non_success_result_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    response = {
        "protocol_version": PROTOCOL_VERSION,
        "status": "succeeded",
        "result": {
            "payload": {},
            "sections": {"sections": []},
            "confidence": None,
            "status": status,
        },
    }
    client = _client(tmp_path, monkeypatch, _FakeProcess(stdout=json.dumps(response).encode()))

    with pytest.raises(AnalysisExtractionError, match="worker result is invalid") as caught:
        client.extract(_track(), timeout=2)

    assert caught.value.stage == "aggregation"


@pytest.mark.parametrize("stdout", [b"", b"not-json", b"{}"])
def test_parent_turns_missing_or_invalid_output_into_aggregation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdout: bytes
) -> None:
    client = _client(tmp_path, monkeypatch, _FakeProcess(stdout=stdout))

    with pytest.raises(AnalysisExtractionError) as caught:
        client.extract(_track(), timeout=2)

    assert caught.value.stage == "aggregation"
    assert "worker" in str(caught.value)


def test_parent_reports_native_signal_as_aggregation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch, _FakeProcess(returncode=-signal.SIGSEGV))

    with pytest.raises(AnalysisExtractionError, match="SIGSEGV") as caught:
        client.extract(_track(), timeout=2)

    assert caught.value.stage == "aggregation"


def test_parent_kills_process_group_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = _FakeProcess(timeout=True)
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr("os.killpg", lambda pid, sig: killed.append((pid, sig)))
    client = _client(tmp_path, monkeypatch, process)

    with pytest.raises(AnalysisExtractionError, match="timed out") as caught:
        client.extract(_track(), timeout=2)

    assert caught.value.stage == "aggregation"
    assert killed == [(process.pid, signal.SIGKILL)]


def test_real_worker_process_returns_a_structured_decode_failure(tmp_path: Path) -> None:
    client = IsolatedAnalysisExtractor({"library": tmp_path}, DspConfig.canonical())

    with pytest.raises(AnalysisExtractionError, match="audio decoding failed") as caught:
        client.extract(_track(), timeout=10)

    assert caught.value.stage == "decode"


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_parent_kills_worker_when_output_exceeds_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stream: str
) -> None:
    module_root = tmp_path / "worker-module"
    module_root.mkdir()
    (module_root / "noisy_worker.py").write_text(
        f"""import sys
import time
sys.{stream}.write(\"x\" * 8192)
sys.{stream}.flush()
time.sleep(60)
"""
    )
    python_path = os.environ.get("PYTHONPATH")
    monkeypatch.setenv(
        "PYTHONPATH",
        str(module_root) if not python_path else f"{module_root}{os.pathsep}{python_path}",
    )
    client = IsolatedAnalysisExtractor(
        {"library": tmp_path},
        DspConfig.canonical(),
        worker_module="noisy_worker",
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )

    with pytest.raises(AnalysisExtractionError, match=f"worker {stream} exceeded"):
        client.extract(_track(), timeout=10)
