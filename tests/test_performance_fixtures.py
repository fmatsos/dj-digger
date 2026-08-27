import sqlite3
from contextlib import closing
from pathlib import Path

from performance.benchmark_queries import ALL_BENCHMARK_CASES
from performance.fixtures import build_catalog
from performance.query_plans import explain, has_full_scan

from dj_digger.catalog.database import Database


def test_build_catalog_has_requested_cardinality(tmp_path: Path) -> None:
    path = build_catalog(tmp_path / "catalog.sqlite", tracks=10, analyses_per_track=5)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT count(*) FROM tracks").fetchone()[0] == 10
        assert connection.execute("SELECT count(*) FROM audio_analysis").fetchone()[0] == 50
        assert connection.execute("SELECT count(*) FROM track_events").fetchone()[0] == 20


def test_build_catalog_alternates_history_and_finishes_with_success(tmp_path: Path) -> None:
    path = build_catalog(tmp_path / "catalog.sqlite", tracks=1, analyses_per_track=5)

    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            "SELECT id, analysis_status, payload_json FROM audio_analysis ORDER BY id"
        ).fetchall()

    assert [(row[0], row[1]) for row in rows] == [
        (1, "succeeded"),
        (2, "failed"),
        (3, "succeeded"),
        (4, "failed"),
        (5, "succeeded"),
    ]
    assert rows[-1][2] == '{"attempt":5,"bpm":121.0,"key":"1A"}'


def test_benchmark_cases_cover_v6_and_v7_operations() -> None:
    names = {case.name for case in ALL_BENCHMARK_CASES}

    assert names == {
        "database_open",
        "status_counts",
        "scan_reconciliation_select",
        "scan_reconciliation_update",
        "metadata_eligibility",
        "analysis_eligibility",
        "analysis_history",
        "track_export",
        "analysis_export_selection",
        "latest_analysis_run",
        "library_listing",
        "pagination",
    }


def test_query_plan_helpers_normalize_details(tmp_path: Path) -> None:
    path = build_catalog(tmp_path / "catalog.sqlite", tracks=1, analyses_per_track=1)
    database = Database.open(path)

    details = explain(database, "SELECT * FROM audio_analysis")

    assert details
    assert all(isinstance(detail, str) for detail in details)
    assert has_full_scan(details, "audio_analysis")
    assert has_full_scan(['  scan main."audio_analysis"  '], "audio_analysis")
    assert not has_full_scan(
        ["SEARCH audio_analysis USING INDEX idx_audio_analysis_track_history"],
        "audio_analysis",
    )
    assert not has_full_scan(["SCAN audio_analysis_history"], "audio_analysis")
