"""Parent-side client for isolated single-track audio analysis workers."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from threading import Lock, Thread
from typing import Any, cast

from dj_digger.analysis.extractor import (
    AnalysisExtractionError,
    AnalysisExtractionResult,
    ResultStatus,
    Stage,
)
from dj_digger.analysis.pipeline import TimedAnalysisExtractor
from dj_digger.analysis.worker import MAX_ERROR_LENGTH, PROTOCOL_VERSION
from dj_digger.catalog.models import Track
from dj_digger.config import DspConfig

MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_STDERR_BYTES = 1024 * 1024
_STAGES: frozenset[str] = frozenset(
    {
        "decode",
        "technical",
        "rhythm",
        "spectrum",
        "windows",
        "segmentation",
        "semantics",
        "aggregation",
    }
)


class IsolatedAnalysisExtractor(TimedAnalysisExtractor):
    """Run one fresh Python interpreter per track and validate its response."""

    def __init__(
        self,
        source_roots: Mapping[str, Path],
        dsp: DspConfig,
        *,
        executable: str | None = None,
        worker_module: str = "dj_digger.analysis.worker",
        max_stdout_bytes: int = MAX_RESPONSE_BYTES,
        max_stderr_bytes: int = MAX_STDERR_BYTES,
    ) -> None:
        self._source_roots = dict(source_roots)
        self._dsp = dsp
        self._executable = executable or sys.executable
        self._worker_module = worker_module
        self._max_stdout_bytes = max_stdout_bytes
        self._max_stderr_bytes = max_stderr_bytes

    def extract(self, track: Track, *, timeout: float) -> AnalysisExtractionResult:
        request = self._request(track)
        kwargs: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True
        elif os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        process = subprocess.Popen(
            [self._executable, "-m", self._worker_module],
            **kwargs,
        )
        encoded = json.dumps(request, separators=(",", ":")).encode()
        stdout, stderr = self._communicate_bounded(process, encoded, timeout)
        if process.returncode != 0:
            message = self._exit_message(process.returncode, stderr)
            raise AnalysisExtractionError("aggregation", message)
        return self._parse_response(stdout)

    def _communicate_bounded(
        self, process: subprocess.Popen[bytes], data: bytes, timeout: float
    ) -> tuple[bytes, bytes]:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise RuntimeError("analysis worker pipes are unavailable")
        stdout = bytearray()
        stderr = bytearray()
        overflow: list[str] = []
        overflow_lock = Lock()

        def drain(stream: Any, buffer: bytearray, limit: int, label: str) -> None:
            read = getattr(stream, "read1", stream.read)
            while chunk := read(64 * 1024):
                remaining = max(0, limit - len(buffer))
                buffer.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    with overflow_lock:
                        if not overflow:
                            overflow.append(label)
                            self._kill_process_tree(process)

        threads = (
            Thread(
                target=drain,
                args=(process.stdout, stdout, self._max_stdout_bytes, "stdout"),
                daemon=True,
            ),
            Thread(
                target=drain,
                args=(process.stderr, stderr, self._max_stderr_bytes, "stderr"),
                daemon=True,
            ),
        )
        for thread in threads:
            thread.start()
        try:
            process.stdin.write(data)
            process.stdin.flush()
        except BrokenPipeError:
            pass
        finally:
            process.stdin.close()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._kill_process_tree(process)
            process.wait()
            for thread in threads:
                thread.join()
            raise AnalysisExtractionError(
                "aggregation", f"analysis worker timed out after {timeout:g} seconds"
            ) from None
        for thread in threads:
            thread.join()
        if overflow:
            raise AnalysisExtractionError(
                "aggregation", f"analysis worker {overflow[0]} exceeded its size limit"
            )
        return bytes(stdout), bytes(stderr)

    def _request(self, track: Track) -> dict[str, object]:
        try:
            root = self._source_roots[track.source_id]
        except KeyError:
            raise AnalysisExtractionError(
                "aggregation", f"analysis source is not configured: {track.source_id}"
            ) from None
        return {
            "protocol_version": PROTOCOL_VERSION,
            "path": str((root / track.relative_path).resolve()),
            "track": {
                "source_id": track.source_id,
                "track_id": track.id,
                "relative_path": track.relative_path,
            },
            "dsp": {
                "version": self._dsp.version,
                "sample_rate": self._dsp.sample_rate,
                "channels": self._dsp.channels,
                "fft_window_size": self._dsp.fft_window_size,
                "fft_hop_size": self._dsp.fft_hop_size,
                "bands": {name: list(limits) for name, limits in self._dsp.bands.items()},
                "segmentation_min_seconds": self._dsp.segmentation_min_seconds,
                "segmentation_max_seconds": self._dsp.segmentation_max_seconds,
                "semantic_min_confidence": self._dsp.semantic_min_confidence,
            },
        }

    @staticmethod
    def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
            )
        else:
            process.kill()

    @staticmethod
    def _exit_message(returncode: int, stderr: bytes) -> str:
        if returncode < 0:
            try:
                name = signal.Signals(-returncode).name
            except ValueError:
                name = f"signal {-returncode}"
            return f"analysis worker terminated by {name}"
        detail = stderr.decode(errors="replace").strip()[:MAX_ERROR_LENGTH]
        suffix = f": {detail}" if detail else ""
        return f"analysis worker exited with code {returncode}{suffix}"

    @staticmethod
    def _parse_response(stdout: bytes) -> AnalysisExtractionResult:
        if not stdout:
            raise AnalysisExtractionError("aggregation", "analysis worker returned no output")
        if len(stdout) > MAX_RESPONSE_BYTES:
            raise AnalysisExtractionError("aggregation", "analysis worker response is too large")
        try:
            response = json.loads(stdout)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise AnalysisExtractionError(
                "aggregation", "analysis worker returned invalid JSON"
            ) from None
        if (
            not isinstance(response, Mapping)
            or response.get("protocol_version") != PROTOCOL_VERSION
        ):
            raise AnalysisExtractionError("aggregation", "analysis worker response is invalid")
        status = response.get("status")
        if status == "failed":
            error = response.get("error")
            if not isinstance(error, Mapping):
                raise AnalysisExtractionError("aggregation", "analysis worker error is invalid")
            stage_value = error.get("stage")
            message = error.get("message")
            stage: Stage = (
                cast(Stage, stage_value)
                if isinstance(stage_value, str) and stage_value in _STAGES
                else "aggregation"
            )
            if not isinstance(message, str) or not message:
                raise AnalysisExtractionError("aggregation", "analysis worker error is invalid")
            raise AnalysisExtractionError(stage, message[:MAX_ERROR_LENGTH])
        result = response.get("result")
        if status != "succeeded" or not isinstance(result, Mapping):
            raise AnalysisExtractionError("aggregation", "analysis worker response is invalid")
        payload = result.get("payload")
        sections = result.get("sections")
        confidence = result.get("confidence")
        result_status = result.get("status")
        if (
            not isinstance(payload, Mapping)
            or not isinstance(sections, Mapping)
            or (
                confidence is not None
                and (not isinstance(confidence, int | float) or isinstance(confidence, bool))
            )
            or result_status != "succeeded"
        ):
            raise AnalysisExtractionError("aggregation", "analysis worker result is invalid")
        return AnalysisExtractionResult(
            dict(payload),
            dict(sections),
            None if confidence is None else float(confidence),
            cast(ResultStatus, result_status),
        )
