import subprocess
from pathlib import Path

import pytest

from dj_digger.analysis.ebur128 import (
    EbuR128AnalysisError,
    EbuR128Analyzer,
    parse_ebur128_output,
)

SAMPLE = """
lavfi.r128.S=-12.0
lavfi.r128.S=-10.0
lavfi.r128.S=-8.0
I: -10.8 LUFS
LRA: 4.2 LU
Peak: -0.4 dBFS
"""


def test_parser_extracts_summary_and_percentiles() -> None:
    result = parse_ebur128_output(SAMPLE)
    assert result.integrated_lufs == pytest.approx(-10.8)
    assert result.loudness_range_lu == pytest.approx(4.2)
    assert result.true_peak_dbtp == pytest.approx(-0.4)
    assert result.short_term_lufs_p50 == pytest.approx(-10.0)
    assert result.short_term_lufs_p95 == pytest.approx(-8.2)


def test_parser_accepts_summary_without_short_term_samples() -> None:
    result = parse_ebur128_output("I: -23.0 LUFS\nLRA: 0.0 LU\nPeak: -1.0 dBFS\n")
    assert result.integrated_lufs == -23.0
    assert result.short_term_lufs_p50 is None
    assert result.short_term_lufs_p95 is None


def test_parser_normalizes_recognized_silence_to_null() -> None:
    result = parse_ebur128_output("I: -inf LUFS\nLRA: -inf LU\nPeak: -inf dBFS\n")
    assert result.integrated_lufs is None
    assert result.loudness_range_lu is None
    assert result.true_peak_dbtp is None


def test_analyzer_isolates_locale_and_path_arguments(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def run(argv, **kwargs):
        observed["argv"] = argv
        observed["env"] = kwargs["env"]
        return type("Result", (), {"stdout": SAMPLE, "stderr": "", "returncode": 0})()

    monkeypatch.setattr("dj_digger.analysis.ebur128.subprocess.run", run)
    EbuR128Analyzer().analyze(Path("odd;name [x].wav"), timeout=2.0)
    assert observed["argv"][0:5] == ["ffmpeg", "-nostdin", "-v", "info", "-i"]
    assert observed["argv"][5] == "odd;name [x].wav"
    assert observed["env"]["LC_ALL"] == "C"
    assert observed["env"]["LANG"] == "C"


def test_analyzer_classifies_timeout(monkeypatch) -> None:
    def run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 1)

    monkeypatch.setattr("dj_digger.analysis.ebur128.subprocess.run", run)
    with pytest.raises(EbuR128AnalysisError, match="timed out") as error:
        EbuR128Analyzer().analyze(Path("track.wav"), timeout=1.0)
    assert error.value.stage == "timeout"
