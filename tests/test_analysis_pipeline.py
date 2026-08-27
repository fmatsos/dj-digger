import json
import os
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from threading import Event, Lock
from typing import Any

import pytest

from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.analysis.extractor import AnalysisExtractionError
from dj_digger.analysis.pipeline import AnalysisPipeline, TimedAnalysisExtractor
from dj_digger.analysis.worker_client import IsolatedAnalysisExtractor
from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import ScanRunRepository, SourceRepository, TrackRepository
from dj_digger.config import DspConfig

IDENTITY = AnalysisIdentity(schema_version=2, analyzer_version="test", config_hash="a" * 64)


class RecordingProgress:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    def phase_started(self, name: str, completed: int, total: int) -> None:
        self.events.append(("phase_started", name, completed, total))

    def phase_finished(self, name: str, completed: int, total: int) -> None:
        self.events.append(("phase_finished", name, completed, total))

    def analysis_started(self, *, total: int, completed: int) -> None:
        self.events.append(("analysis_started", total, completed))

    def analysis_advanced(self) -> None:
        self.events.append(("analysis_advanced",))

    def analysis_finished(self) -> None:
        self.events.append(("analysis_finished",))

    def diagnostic(self, level: str, message: str) -> None:
        self.events.append(("diagnostic", level, message))


def _track(database: Database, source_id: str, path: str) -> Track:
    with database.transaction():
        SourceRepository(database).upsert(
            source_id, Path(f"/{source_id}"), set_eligible=True, analyze=True, enabled=True
        )
    scan_id = database.scalar("SELECT id FROM scan_runs WHERE source_id = ?", (source_id,))
    if scan_id is None:
        scan_id = ScanRunRepository(database).start(source_id, scanner_version="test")
    with database.transaction():
        return TrackRepository(database).insert(
            source_id=source_id,
            relative_path=path,
            filename=Path(path).name,
            extension=Path(path).suffix,
            size_bytes=10,
            mtime_ns=20,
            scan_id=int(scan_id),
        )


def _pipeline(database: Database, calls: list[str]):
    from dj_digger.analysis.pipeline import AnalysisPipeline

    def extract(track: Any) -> Mapping[str, object]:
        calls.append(track.relative_path)
        return {"path": track.relative_path}

    return AnalysisPipeline(database, IDENTITY, extract)


def test_pipeline_filters_then_limits_pending_tracks(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/A.flac")
    _track(database, "one", "Techno/B.flac")
    _track(database, "two", "House/C.flac")
    calls: list[str] = []

    result = _pipeline(database, calls).run(
        source_id="one", path_prefix="House", limit=1, workers=2
    )

    assert result.eligible == 1
    assert result.analyzed == 1
    assert result.reused == result.failed == 0
    assert calls == ["House/A.flac"]


def test_pipeline_reuses_unchanged_tracks_on_a_second_run(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/A.flac")
    calls: list[str] = []
    pipeline = _pipeline(database, calls)

    first = pipeline.run()
    second = pipeline.run()

    assert first.analyzed == 1
    assert second.eligible == 0
    assert second.analyzed == second.failed == 0
    assert second.reused == second.eligible
    assert calls == ["House/A.flac"]


def test_pipeline_force_selects_reusable_tracks_without_duplicate_persistence(
    tmp_path: Path,
) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/A.flac")
    calls: list[str] = []
    pipeline = _pipeline(database, calls)
    pipeline.run()

    result = pipeline.run(force=True)

    assert result.eligible == result.reused == 1
    assert result.analyzed == result.failed == 0
    assert calls == ["House/A.flac"]
    assert database.scalar("SELECT COUNT(*) FROM audio_analysis") == 1


def test_pipeline_progress_starts_at_reused_count(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/A.flac")
    calls: list[str] = []
    _pipeline(database, calls).run()
    progress = RecordingProgress()

    AnalysisPipeline(database, IDENTITY, lambda track: {}, progress=progress).run(force=True)

    assert progress.events == [
        ("analysis_started", 1, 1),
        ("analysis_finished",),
    ]


def test_pipeline_progress_advances_after_every_persisted_outcome(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/A.flac")
    _track(database, "one", "House/B.flac")
    progress = RecordingProgress()

    def extract(track: Track) -> Mapping[str, object]:
        if track.relative_path.endswith("B.flac"):
            raise AnalysisExtractionError("decode", "controlled failure")
        return {"path": track.relative_path}

    AnalysisPipeline(database, IDENTITY, extract, progress=progress).run()

    assert progress.events == [
        ("analysis_started", 2, 0),
        ("analysis_advanced",),
        ("diagnostic", "error", "House/B.flac: controlled failure"),
        ("analysis_advanced",),
        ("analysis_finished",),
    ]


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_pipeline_rejects_non_positive_track_timeout(
    tmp_path: Path, timeout: float
) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()

    with pytest.raises(ValueError, match="track timeout must be positive"):
        AnalysisPipeline(database, IDENTITY, lambda track: {}).run(track_timeout=timeout)


def test_pipeline_continues_after_isolated_worker_failure(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/crash.flac")
    _track(database, "one", "House/next.flac")
    calls: list[str] = []

    class TimedExtractor(TimedAnalysisExtractor):
        def extract(self, track: Track, *, timeout: float) -> Mapping[str, object]:
            calls.append(track.relative_path)
            if track.relative_path.endswith("crash.flac"):
                raise AnalysisExtractionError("aggregation", "worker terminated by SIGSEGV")
            return {"path": track.relative_path}

    result = AnalysisPipeline(database, IDENTITY, TimedExtractor()).run(
        workers=1, track_timeout=7
    )

    assert calls == ["House/crash.flac", "House/next.flac"]
    assert (result.status, result.analyzed, result.failed) == ("partial", 1, 1)

    retry = AnalysisPipeline(database, IDENTITY, TimedExtractor()).run(track_timeout=7)
    assert retry.eligible == 1


def test_callable_extractor_with_extract_attribute_stays_on_callable_contract(
    tmp_path: Path,
) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/A.flac")
    calls: list[str] = []

    class CallableExtractor:
        def __call__(self, track: Track) -> Mapping[str, object]:
            calls.append(track.relative_path)
            return {"path": track.relative_path}

        def extract(self, track: Track, *, timeout: float) -> Mapping[str, object]:
            raise AssertionError("an unrelated extract attribute must not select timed mode")

    result = AnalysisPipeline(database, IDENTITY, CallableExtractor()).run()

    assert result.analyzed == 1
    assert calls == ["House/A.flac"]


def test_native_sigsegv_worker_does_not_stop_the_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_root = tmp_path / "worker-module"
    module_root.mkdir()
    (module_root / "controlled_worker.py").write_text(
        """import json
import os
import signal
import sys

request = json.load(sys.stdin)
if request[\"track\"][\"relative_path\"].endswith(\"crash.flac\"):
    os.kill(os.getpid(), signal.SIGSEGV)
json.dump({
    \"protocol_version\": 1,
    \"status\": \"succeeded\",
    \"result\": {
        \"payload\": {\"path\": request[\"track\"][\"relative_path\"]},
        \"sections\": {\"sections\": []},
        \"confidence\": None,
        \"status\": \"succeeded\",
    },
}, sys.stdout)
"""
    )
    python_path = os.environ.get("PYTHONPATH")
    monkeypatch.setenv(
        "PYTHONPATH",
        str(module_root) if not python_path else f"{module_root}{os.pathsep}{python_path}",
    )
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/crash.flac")
    _track(database, "one", "House/next.flac")
    extractor = IsolatedAnalysisExtractor(
        {"one": tmp_path}, DspConfig.canonical(), worker_module="controlled_worker"
    )

    result = AnalysisPipeline(database, IDENTITY, extractor).run(
        workers=1, track_timeout=10
    )

    assert (result.status, result.analyzed, result.failed) == ("partial", 1, 1)
    failure = database.execute(
        "SELECT payload_json FROM audio_analysis WHERE analysis_status = 'failed'"
    ).fetchone()[0]
    assert json.loads(failure) == {
        "error": "analysis worker terminated by SIGSEGV",
        "stage": "aggregation",
    }


def test_pipeline_progress_closes_an_empty_selection(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    progress = RecordingProgress()

    AnalysisPipeline(database, IDENTITY, lambda track: {}, progress=progress).run()

    assert progress.events == [
        ("analysis_started", 0, 0),
        ("analysis_finished",),
    ]


def test_pipeline_force_reports_partial_when_reuse_and_pending_failure_coexist(
    tmp_path: Path,
) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/reusable.flac")
    _track(database, "one", "House/failing.flac")
    calls: list[str] = []

    def extract(track: Track) -> Mapping[str, object]:
        calls.append(track.relative_path)
        if track.relative_path.endswith("failing.flac") and len(calls) > 2:
            raise AnalysisExtractionError("spectrum", "controlled failure")
        return {"path": track.relative_path}

    pipeline = AnalysisPipeline(database, IDENTITY, extract)
    pipeline.run()
    failing_id = database.scalar("SELECT id FROM tracks WHERE relative_path = 'House/failing.flac'")
    database.execute("DELETE FROM current_track_analysis WHERE track_id = ?", (failing_id,))
    database.execute("DELETE FROM audio_analysis WHERE track_id = ?", (failing_id,))
    database.commit()
    result = pipeline.run(force=True)
    assert result.reused == 1
    assert result.failed == 1
    assert result.status == "partial"


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [([], "succeeded"), (["ok"], "succeeded"), (["ok", "fail"], "partial"), (["fail"], "failed")],
)
def test_pipeline_aggregates_empty_success_partial_and_failure_statuses(
    tmp_path: Path, outcomes: list[str], expected: str
) -> None:
    from dj_digger.analysis.extractor import AnalysisExtractionError
    from dj_digger.analysis.pipeline import AnalysisPipeline

    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    for index, outcome in enumerate(outcomes):
        _track(database, "one", f"House/{index}.flac")

    def extract(track: Track) -> Mapping[str, object]:
        if outcomes[int(track.relative_path.split("/")[-1].split(".")[0])] == "fail":
            raise AnalysisExtractionError("spectrum", "controlled failure")
        return {"path": track.relative_path}

    result = AnalysisPipeline(database, IDENTITY, extract).run()
    assert result.status == expected
    row = database.execute(
        "SELECT status, eligible, analyzed, failed FROM analysis_runs WHERE id = ?",
        (result.run_id,),
    ).fetchone()
    assert row == (expected, len(outcomes), outcomes.count("ok"), outcomes.count("fail"))
    if "fail" in outcomes:
        payload = database.execute(
            "SELECT payload_json FROM audio_analysis WHERE analysis_status = 'failed'"
        ).fetchone()[0]
        assert json.loads(payload)["stage"] == "spectrum"
        event = database.execute(
            "SELECT payload_json FROM track_events WHERE event_type = 'analysis_failed'"
        ).fetchone()[0]
        assert json.loads(event)["stage"] == "spectrum"


def test_pipeline_commits_each_outcome_before_extracting_the_next_track(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.sqlite"
    database = Database.open(catalog_path)
    database.migrate()
    _track(database, "one", "House/A.flac")
    _track(database, "one", "House/B.flac")
    observed_runs: list[tuple[str, int, int]] = []
    observed_attempts: list[int] = []

    def extract(track: Track) -> Mapping[str, object]:
        observer = sqlite3.connect(catalog_path)
        try:
            if track.relative_path.endswith("A.flac"):
                observed_runs.append(
                    observer.execute(
                        "SELECT status, eligible, analyzed FROM analysis_runs"
                    ).fetchone()
                )
            else:
                observed_attempts.append(
                    observer.execute("SELECT COUNT(*) FROM audio_analysis").fetchone()[0]
                )
        finally:
            observer.close()
        return {"path": track.relative_path}

    result = AnalysisPipeline(database, IDENTITY, extract).run()

    assert observed_runs == [("running", 2, 0)]
    assert observed_attempts == [1]
    assert (result.status, result.analyzed, result.failed) == ("succeeded", 2, 0)


def test_pipeline_never_runs_more_extractions_than_workers(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    for index in range(4):
        _track(database, "one", f"House/{index}.flac")
    lock = Lock()
    both_started = Event()
    active = 0
    peak_active = 0

    def extract(track: Track) -> Mapping[str, object]:
        nonlocal active, peak_active
        with lock:
            active += 1
            peak_active = max(peak_active, active)
            if active == 2:
                both_started.set()
        if not both_started.wait(timeout=2):
            raise TimeoutError("two extraction workers did not become active")
        with lock:
            active -= 1
        return {"path": track.relative_path}

    result = AnalysisPipeline(database, IDENTITY, extract).run(workers=2)

    assert peak_active == 2
    assert (result.status, result.analyzed, result.failed) == ("succeeded", 4, 0)
    assert database.scalar("SELECT COUNT(*) FROM audio_analysis") == 4


def test_pipeline_reconciles_interrupted_run_before_pending_selection(tmp_path: Path) -> None:
    from dj_digger.analysis.persistence import AnalysisOutcome, AnalysisPersistence

    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    first_track = _track(database, "one", "House/A.flac")
    _track(database, "one", "House/B.flac")
    persistence = AnalysisPersistence(database)
    old_run_id = persistence.start_run(
        IDENTITY, eligible=2, reused=0, started_at="old-start"
    )
    persistence.persist_outcome(
        old_run_id,
        IDENTITY,
        AnalysisOutcome(first_track, {"path": first_track.relative_path}, None, "aggregation"),
        occurred_at="old-outcome",
    )
    calls: list[str] = []

    result = _pipeline(database, calls).run()

    old_run = database.execute(
        "SELECT status, analyzed, failed, finished_at FROM analysis_runs WHERE id = ?",
        (old_run_id,),
    ).fetchone()
    assert old_run[:3] == ("partial", 1, 0)
    assert old_run[3] is not None
    assert calls == ["House/B.flac"]
    assert (result.status, result.analyzed, result.failed) == ("succeeded", 1, 0)


def test_pipeline_propagates_outcome_persistence_error_and_leaves_run_running(
    tmp_path: Path,
) -> None:
    from dj_digger.analysis.extractor import AnalysisExtractionResult

    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    _track(database, "one", "House/A.flac")

    def extract(track: Track) -> AnalysisExtractionResult:
        return AnalysisExtractionResult(
            {"path": track.relative_path},
            {"sections": ["not an object"]},
            None,
            "succeeded",
        )

    with pytest.raises(ValueError, match="analysis section must be an object"):
        AnalysisPipeline(database, IDENTITY, extract).run()

    assert database.execute(
        "SELECT status, analyzed, failed FROM analysis_runs"
    ).fetchall() == [("running", 0, 0)]
    assert database.scalar("SELECT COUNT(*) FROM audio_analysis") == 0


def test_concurrent_pipeline_fails_without_reconciling_the_active_run(tmp_path: Path) -> None:
    from dj_digger.analysis.persistence import AnalysisPersistence

    catalog_path = tmp_path / "catalog.sqlite"
    active_database = Database.open(catalog_path)
    active_database.migrate()
    _track(active_database, "one", "House/A.flac")
    run_id = AnalysisPersistence(active_database).start_run(
        IDENTITY, eligible=1, reused=0, started_at="active-start"
    )
    active_row = active_database.execute(
        "SELECT status, eligible, analyzed, reused, failed, finished_at "
        "FROM analysis_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    competing_database = Database.open(catalog_path)
    calls: list[str] = []

    with active_database.advisory_lock("analysis-pipeline"):
        with pytest.raises(RuntimeError, match="already held"):
            _pipeline(competing_database, calls).run()

    assert competing_database.execute(
        "SELECT status, eligible, analyzed, reused, failed, finished_at "
        "FROM analysis_runs WHERE id = ?",
        (run_id,),
    ).fetchone() == active_row
    assert calls == []
    assert competing_database.scalar("SELECT COUNT(*) FROM analysis_runs") == 1
