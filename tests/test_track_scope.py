"""One shared scope filter, and analysis selection without a query per track."""

from pathlib import Path

import pytest

from dj_digger.core.analysis.config import AnalysisIdentity
from dj_digger.core.catalog.database import Database
from dj_digger.core.catalog.queries import TrackScope, escape_like_prefix
from dj_digger.core.catalog.repositories import (
    ScanRunRepository,
    SourceRepository,
    TrackRepository,
)

IDENTITY = AnalysisIdentity(2, "analyzer/1", "hash")


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("plain", "plain"),
        ("100%", r"100\%"),
        ("a_b", r"a\_b"),
        ("back\\slash", r"back\\slash"),
        (r"mix\%_", r"mix\\\%\_"),
    ],
)
def test_like_wildcards_and_the_escape_character_are_all_escaped(
    prefix: str, expected: str
) -> None:
    assert escape_like_prefix(prefix) == expected


def test_an_empty_scope_adds_no_predicate_and_no_parameter() -> None:
    clause, parameters = TrackScope().as_sql("t")

    assert clause == ""
    assert parameters == []


def test_a_scope_binds_its_values_and_never_inlines_them() -> None:
    clause, parameters = TrackScope(source_id="lib", path_prefix="house/").as_sql("t")

    assert clause == " AND t.source_id = ? AND t.relative_path LIKE ? ESCAPE '\\'"
    assert parameters == ["lib", "house/%"]
    assert "lib" not in clause


def _catalog(tmp_path: Path) -> Database:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    with database.transaction():
        SourceRepository(database).upsert(
            "lib", tmp_path / "lib", set_eligible=True, analyze=True, enabled=True
        )
    return database


def _add_track(database: Database, relative_path: str) -> None:
    """Insert through the real repository so the schema stays the source of truth."""
    scan_id = database.scalar("SELECT id FROM scan_runs WHERE source_id = ?", ("lib",))
    if scan_id is None:
        scan_id = ScanRunRepository(database).start("lib", scanner_version="test")
    with database.transaction():
        TrackRepository(database).insert(
            source_id="lib",
            relative_path=relative_path,
            filename=Path(relative_path).name,
            extension=Path(relative_path).suffix,
            size_bytes=10,
            mtime_ns=20,
            scan_id=int(scan_id),
        )


def test_a_literal_wildcard_prefix_does_not_match_every_track(tmp_path: Path) -> None:
    """An unescaped `_` would make `a_b` match `axb` too."""
    database = _catalog(tmp_path)
    _add_track(database, "a_b/one.flac")
    _add_track(database, "axb/two.flac")

    matched = TrackRepository(database).eligible_for_analysis(source_id=None, path_prefix="a_b")

    assert [track.relative_path for track in matched] == ["a_b/one.flac"]
    database.close()


def test_selecting_analysis_work_costs_a_bounded_number_of_queries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reusability must be decided in SQL, not with one query per track."""
    database = _catalog(tmp_path)
    for index in range(40):
        _add_track(database, f"track-{index:03d}.flac")

    repository = TrackRepository(database)
    queries: list[str] = []
    real_execute = Database.execute

    def spy(self: Database, query: str, parameters: object = ()) -> object:
        queries.append(query)
        return real_execute(self, query, parameters)  # type: ignore[arg-type]

    monkeypatch.setattr(Database, "execute", spy)

    tracks = repository.eligible_for_analysis(source_id=None, path_prefix=None)
    reusable = repository.ids_with_current_analysis(
        schema_version=IDENTITY.schema_version,
        analyzer_version=IDENTITY.analyzer_version,
        config_hash=IDENTITY.config_hash,
        source_id=None,
        path_prefix=None,
    )

    assert len(tracks) == 40
    assert reusable == set()
    assert len(queries) == 2, f"expected 2 queries for 40 tracks, got {len(queries)}"
    database.close()
