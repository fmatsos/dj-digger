"""Read-only, privacy-bounded projections over Catalog V9."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from dj_digger.catalog.database import Database
from dj_digger.catalog.migrations import CURRENT_VERSION
from dj_digger.curation.models import (
    AnalysisDetails,
    AnalysisRunSummary,
    AnalysisStatus,
    AnalysisWindows,
    AudioFormat,
    CandidateDetails,
    CandidateDetailsV1,
    CandidateIdentity,
    CandidateRef,
    CandidateSearchV1,
    CandidateSummary,
    DiscoveryMetadata,
    FacetSummary,
    FacetValue,
    LibraryOverviewV1,
    MasteringSummary,
    QualityStatus,
    SearchFilters,
    SectionSummary,
    SourceSummary,
)


class CurationCatalogError(RuntimeError):
    """Sanitized public error raised by the curation read model."""


@dataclass(frozen=True)
class _Row:
    source_id: str
    track_id: int
    path: str
    filename: str
    size: int
    mtime: int
    title: str | None
    artist: str | None
    album_artist: str | None
    album: str | None
    genre: str | None
    year: str | None
    grouping: str | None
    comment: str | None
    tag_bpm: float | None
    tag_key: str | None
    duration: float | None
    codec: str | None
    container: str | None
    lossless: bool | None
    bit_depth: int | None
    sample_rate: int | None
    bitrate: int | None
    fingerprint: str | None
    analysis_id: int | None
    analysis_status: str
    analysis_confidence: float | None
    payload: dict[str, Any]
    sections: tuple[dict[str, Any], ...]
    mastering: dict[str, Any]
    group_key: str
    group_size: int = 1
    quality_status: QualityStatus = "unverified_unfingerprinted"
    matched_suppressed: bool = False
    group_values: tuple[str, ...] = ()


class CurationCatalog:
    """Build bounded curation DTOs from a fresh read-only SQLite snapshot."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.resolve()

    def _open(self) -> Database:
        try:
            database = Database.open_read_only(self._database_path)
            version = int(database.scalar("PRAGMA user_version") or 0)
            if version != CURRENT_VERSION:
                database.close()
                raise CurationCatalogError("catalog version is unsupported; prepare a Catalog V9")
            return database
        except CurationCatalogError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise CurationCatalogError("catalog is unavailable or cannot be read") from error

    def _rows(self, database: Database) -> list[_Row]:
        query = """
            SELECT t.source_id, t.id, t.relative_path, t.filename, t.size_bytes, t.mtime_ns,
                   e.title, e.artist, e.album_artist, e.album, e.genre, e.year, e.grouping,
                   e.comment, e.tag_bpm, e.tag_initial_key,
                   x.duration_seconds, x.codec, x.container, x.lossless, x.bit_depth,
                   x.sample_rate, x.bitrate,
                   CASE WHEN af.input_size_bytes = t.size_bytes
                              AND af.input_mtime_ns = t.mtime_ns
                              AND af.fingerprint_hash <> ''
                        THEN af.fingerprint_hash END AS fingerprint,
                   a.id, COALESCE(a.analysis_status, 'missing'), a.analysis_confidence,
                   a.input_size_bytes, a.input_mtime_ns,
                   CASE WHEN a.analysis_status = 'succeeded'
                              AND a.input_size_bytes = t.size_bytes
                              AND a.input_mtime_ns = t.mtime_ns
                        THEN a.payload_json ELSE NULL END,
                   cm.integrated_lufs, cm.loudness_range_lu, cm.true_peak_dbtp,
                   cm.peak_to_loudness_ratio_db, dj.required_gain_db,
                   dj.available_gain_db, dj.gain_deficit_db
            FROM tracks t
            JOIN library_sources s ON s.source_id = t.source_id AND s.set_eligible = 1
            LEFT JOIN embedded_metadata e ON e.track_id = t.id
            LEFT JOIN technical_audio_metadata x ON x.track_id = t.id
                AND x.input_size_bytes = t.size_bytes AND x.input_mtime_ns = t.mtime_ns
            LEFT JOIN audio_fingerprints af ON af.track_id = t.id
            LEFT JOIN audio_analysis a ON a.id = (
                SELECT latest.id FROM audio_analysis latest
                WHERE latest.track_id = t.id ORDER BY latest.id DESC LIMIT 1
            )
            LEFT JOIN current_mastering_analysis cm ON cm.track_id = t.id
                AND EXISTS (
                    SELECT 1 FROM mastering_analysis ma
                    WHERE ma.id = cm.mastering_analysis_id
                      AND ma.input_size_bytes = t.size_bytes
                      AND ma.input_mtime_ns = t.mtime_ns
                )
            LEFT JOIN current_dj_analysis dj ON dj.track_id = t.id
            WHERE t.presence_status = 'present'
            ORDER BY t.id
        """
        records = database.execute(query).fetchall()
        rows: list[_Row] = []
        section_cache: dict[int, tuple[dict[str, Any], ...]] = {}
        for record in records:
            (
                source_id,
                track_id,
                path,
                filename,
                size,
                mtime,
                title,
                artist,
                album_artist,
                album,
                genre,
                year,
                grouping,
                comment,
                tag_bpm,
                tag_key,
                duration,
                codec,
                container,
                lossless,
                bit_depth,
                sample_rate,
                bitrate,
                fingerprint,
                analysis_id,
                analysis_status,
                analysis_confidence,
                analysis_size,
                analysis_mtime,
                raw_payload,
                integrated,
                lra,
                true_peak,
                plr,
                required_gain,
                available_gain,
                gain_deficit,
            ) = record
            current_analysis = (
                analysis_status == "succeeded" and analysis_size == size and analysis_mtime == mtime
            )
            public_analysis_status = (
                "failed"
                if analysis_id is not None and analysis_status == "failed"
                else "ok"
                if current_analysis
                else "missing"
            )
            payload = _json_object(raw_payload)
            aid = None if analysis_id is None else int(analysis_id)
            if current_analysis and aid is not None and aid not in section_cache:
                section_cache[aid] = tuple(
                    _json_object(item[0])
                    for item in database.execute(
                        "SELECT payload_json FROM track_sections WHERE audio_analysis_id = ? "
                        "ORDER BY section_index",
                        (aid,),
                    ).fetchall()
                )
            mastering = {
                "integrated_lufs": integrated,
                "loudness_range_lu": lra,
                "true_peak_dbtp": true_peak,
                "peak_to_loudness_ratio_db": plr,
                "required_gain_db": required_gain,
                "available_gain_db": available_gain,
                "gain_deficit_db": gain_deficit,
            }
            fp = None if fingerprint is None else str(fingerprint)
            relative_path = str(path)
            if Path(relative_path).is_absolute():
                raise CurationCatalogError("catalog contains an invalid relative track path")
            rows.append(
                _Row(
                    str(source_id),
                    int(track_id),
                    relative_path,
                    str(filename),
                    int(size),
                    int(mtime),
                    _optional_str(title),
                    _optional_str(artist),
                    _optional_str(album_artist),
                    _optional_str(album),
                    _optional_str(genre),
                    _optional_str(year),
                    _optional_str(grouping),
                    _optional_str(comment),
                    _optional_float(tag_bpm),
                    _optional_str(tag_key),
                    _optional_float(duration),
                    _optional_str(codec),
                    _optional_str(container),
                    None if lossless is None else bool(lossless),
                    _optional_int(bit_depth),
                    _optional_int(sample_rate),
                    _optional_int(bitrate),
                    fp,
                    aid,
                    public_analysis_status,
                    _optional_float(analysis_confidence),
                    payload,
                    section_cache[aid] if current_analysis and aid is not None else (),
                    mastering,
                    fp or f"track:{track_id}",
                )
            )
        return _rank_rows(rows)

    def overview(self) -> LibraryOverviewV1:
        database = self._open()
        try:
            with database.read_transaction():
                rows = self._rows(database)
                available_count = int(
                    database.scalar(
                        """SELECT COUNT(*) FROM tracks t JOIN library_sources s
                           ON s.source_id = t.source_id
                           WHERE t.presence_status = 'present' AND s.set_eligible = 1"""
                    )
                    or 0
                )
                fingerprinted_count = int(
                    database.scalar(
                        """SELECT COUNT(*) FROM tracks t
                           JOIN library_sources s ON s.source_id = t.source_id
                           JOIN audio_fingerprints af ON af.track_id = t.id
                           WHERE t.presence_status = 'present' AND s.set_eligible = 1
                             AND af.fingerprint_hash <> ''
                             AND af.input_size_bytes = t.size_bytes
                             AND af.input_mtime_ns = t.mtime_ns"""
                    )
                    or 0
                )
                source_records = database.execute(
                    """SELECT s.source_id, r.finished_at FROM library_sources s
                       LEFT JOIN scan_runs r ON r.id = s.last_successful_scan_id
                       ORDER BY s.source_id"""
                ).fetchall()
                latest = database.execute(
                    "SELECT status, started_at, finished_at, eligible, analyzed, reused, failed "
                    "FROM analysis_runs ORDER BY id DESC LIMIT 1"
                ).fetchone()
        finally:
            database.close()
        counts = {
            status: sum(row.analysis_status == status for row in rows)
            for status in ("ok", "failed", "missing")
        }
        quality = {
            status: sum(row.quality_status == status for row in rows)
            for status in ("unique", "verified_best", "best_effort", "unverified_unfingerprinted")
        }
        run = AnalysisRunSummary(
            status=None if latest is None else str(latest[0]),
            started_at=None if latest is None else _optional_str(latest[1]),
            finished_at=None if latest is None else _optional_str(latest[2]),
            eligible=0 if latest is None else int(latest[3]),
            analyzed=0 if latest is None else int(latest[4]),
            reused=0 if latest is None else int(latest[5]),
            failed=0 if latest is None else int(latest[6]),
        )
        facets = {
            name: _facet(rows, name)
            for name in ("genre", "year", "key", "analysis_status", "quality_status")
        }
        return LibraryOverviewV1(
            catalog_version=CURRENT_VERSION,
            available_tracks=available_count,
            candidates=len(rows),
            analysis_ok=counts["ok"],
            analysis_failed=counts["failed"],
            analysis_missing=counts["missing"],
            fingerprinted=fingerprinted_count,
            quality_status_counts=quality,
            latest_analysis=run,
            sources=tuple(
                SourceSummary(
                    source_id=str(item[0]), last_successful_scan_at=_optional_str(item[1])
                )
                for item in source_records
            ),
            facets=facets,
        )

    def search(
        self, filters: SearchFilters, *, limit: int = 25, cursor: str | None = None
    ) -> CandidateSearchV1:
        if limit < 1 or limit > 50:
            raise CurationCatalogError("limit must be between 1 and 50")
        after = _decode_cursor(cursor, filters, limit) if cursor else 0
        database = self._open()
        try:
            with database.read_transaction():
                rows = self._rows(database)
        finally:
            database.close()
        selected = [row for row in rows if row.track_id > after and _matches(row, filters)]
        selected = selected[:limit]
        next_cursor = None
        if (
            len(selected) == limit
            and len(
                [
                    row
                    for row in rows
                    if row.track_id > selected[-1].track_id and _matches(row, filters)
                ]
            )
            > 0
        ):
            next_cursor = _encode_cursor(selected[-1].track_id, filters, limit)
        return CandidateSearchV1(
            candidates=tuple(
                _summary(_copy_row(row, matched_suppressed=_suppressed_match(row, filters.query)))
                for row in selected
            ),
            next_cursor=next_cursor,
        )

    def get_candidates(self, refs: Sequence[CandidateRef]) -> CandidateDetailsV1:
        if not 1 <= len(refs) <= 20:
            raise CurationCatalogError("candidates must contain between 1 and 20 references")
        keys = [(ref.source_id, ref.track_id) for ref in refs]
        if len(set(keys)) != len(keys):
            raise CurationCatalogError("candidate references must be unique")
        database = self._open()
        try:
            with database.read_transaction():
                rows = self._rows(database)
        finally:
            database.close()
        by_key = {(row.source_id, row.track_id): row for row in rows}
        if any(key not in by_key for key in keys):
            raise CurationCatalogError("candidate reference is unknown or unavailable")
        return CandidateDetailsV1(candidates=tuple(_details(by_key[key]) for key in keys))


def _rank_rows(rows: list[_Row]) -> list[_Row]:
    groups: dict[str, list[_Row]] = {}
    for row in rows:
        groups.setdefault(row.group_key, []).append(row)
    result: list[_Row] = []
    for group_key, members in groups.items():
        winner = min(members, key=_quality_key)
        group_values = tuple(
            value
            for member in members
            for value in (
                member.title,
                member.artist,
                member.album_artist,
                member.album,
                member.genre,
                member.grouping,
                member.comment,
                member.filename,
                member.path,
            )
            if value is not None
        )
        if winner.fingerprint is None:
            status: QualityStatus = "unverified_unfingerprinted"
        elif len(members) == 1:
            status = "unique"
        elif all(_quality_complete(member) for member in members):
            status = "verified_best"
        else:
            status = "best_effort"
        result.append(
            _copy_row(
                winner,
                group_size=len(members),
                quality_status=status,
                group_values=group_values,
            )
        )
    return sorted(result, key=lambda row: row.track_id)


def _copy_row(row: _Row, **changes: Any) -> _Row:
    values = row.__dict__ | changes
    return _Row(**values)


def _quality_key(row: _Row) -> tuple[object, ...]:
    tier = 0 if row.lossless is True else 1 if row.lossless is False else 2
    bit_depth = row.bit_depth if row.lossless is True and row.bit_depth is not None else -1
    bitrate = row.bitrate if row.lossless is False and row.bitrate is not None else -1
    sample_rate = row.sample_rate if row.sample_rate is not None else -1
    return (tier, -bit_depth, -bitrate, -sample_rate, row.source_id, row.path, row.track_id)


def _quality_complete(row: _Row) -> bool:
    return (
        row.lossless is not None
        and row.sample_rate is not None
        and (row.bit_depth is not None if row.lossless else row.bitrate is not None)
    )


def _matches(row: _Row, filters: SearchFilters) -> bool:
    if filters.source_ids and row.source_id not in filters.source_ids:
        return False
    if filters.genres and (row.genre is None or row.genre not in filters.genres):
        return False
    if filters.keys and (row.payload.get("key") or row.tag_key) not in filters.keys:
        return False
    if filters.year_min is not None and (row.year is None or _year(row.year) < filters.year_min):
        return False
    if filters.year_max is not None and (row.year is None or _year(row.year) > filters.year_max):
        return False
    bpm = _number(row.payload.get("bpm"))
    if bpm is None:
        bpm = row.tag_bpm
    if filters.bpm_min is not None and (bpm is None or bpm < filters.bpm_min):
        return False
    if filters.bpm_max is not None and (bpm is None or bpm > filters.bpm_max):
        return False
    if filters.duration_min_seconds is not None and (
        row.duration is None or row.duration < filters.duration_min_seconds
    ):
        return False
    if filters.duration_max_seconds is not None and (
        row.duration is None or row.duration > filters.duration_max_seconds
    ):
        return False
    if filters.lossless is not None and row.lossless is not filters.lossless:
        return False
    if filters.analysis_required is True and row.analysis_status != "ok":
        return False
    if filters.query:
        needle = filters.query.casefold()
        values: tuple[str | None, ...] = (
            row.title,
            row.artist,
            row.album_artist,
            row.album,
            row.genre,
            row.grouping,
            row.comment,
            row.filename,
            row.path,
        )
        values = values + row.group_values
        if not any(value is not None and needle in value.casefold() for value in values):
            return False
    return True


def _suppressed_match(row: _Row, query: str | None) -> bool:
    if not query:
        return False
    needle = query.casefold()
    winner_values = (
        row.title,
        row.artist,
        row.album_artist,
        row.album,
        row.genre,
        row.grouping,
        row.comment,
        row.filename,
        row.path,
    )
    winner_matches = any(
        value is not None and needle in value.casefold() for value in winner_values
    )
    return not winner_matches and any(needle in value.casefold() for value in row.group_values)


def _summary(row: _Row) -> CandidateSummary:
    return CandidateSummary(
        identity=CandidateIdentity(source_id=row.source_id, track_id=row.track_id, path=row.path),
        title=row.title,
        artist=row.artist,
        album=row.album,
        genre=row.genre,
        year=row.year,
        duration_seconds=row.duration,
        bpm=_number(row.payload.get("bpm")) or row.tag_bpm,
        key=_optional_str(row.payload.get("key")) or row.tag_key,
        lossless=row.lossless,
        analysis_status=cast(AnalysisStatus, row.analysis_status),
        analysis_confidence=row.analysis_confidence,
        quality_status=row.quality_status,
        duplicate_members=row.group_size,
        matched_on_suppressed_variant=row.matched_suppressed,
    )


def _details(row: _Row) -> CandidateDetails:
    payload = row.payload if row.analysis_status == "ok" else {}
    energy = {
        name: _number(payload.get(name)) for name in ("sub_energy", "low_energy", "low_mid_energy")
    }
    density = {
        name: _number(payload.get(name))
        for name in ("kick_density", "bass_density", "onset_density")
    }
    windows: dict[str, dict[str, dict[str, object | None]]] = {"intro": {}, "outro": {}}
    for side in windows:
        for bars in (8, 16, 32, 64):
            prefix = f"{side}_{bars}_"
            windows[side][str(bars)] = {
                "available": bool(payload.get(prefix + "available", False)),
                **{
                    name: payload.get(prefix + name)
                    for name in (
                        "bpm",
                        "beat_stability",
                        "sub_energy",
                        "low_energy",
                        "low_mid_energy",
                        "kick_strength",
                        "kick_density",
                        "bass_density",
                        "loudness_lufs",
                        "onset_density",
                        "spectral_centroid",
                    )
                },
            }
    sections = tuple(
        SectionSummary(
            index=int(item.get("index", index)),
            start=float(item.get("start", 0.0)),
            end=float(item.get("end", 0.0)),
            facts={
                key: item[key]
                for key in (
                    "bpm",
                    "beat_stability",
                    "sub_energy",
                    "low_energy",
                    "low_mid_energy",
                    "kick_strength",
                    "kick_density",
                    "bass_density",
                    "onset_density",
                    "spectral_centroid",
                    "loudness_lufs",
                )
                if key in item
            },
            semantic_label=_optional_str(item.get("semantic_label")),
            semantic_confidence=_number(item.get("semantic_confidence")),
            transition_suitability_in=_number(item.get("transition_suitability_in")),
            transition_suitability_out=_number(item.get("transition_suitability_out")),
        )
        for index, item in enumerate(row.sections)
    )
    return CandidateDetails(
        identity=CandidateIdentity(source_id=row.source_id, track_id=row.track_id, path=row.path),
        discovery=DiscoveryMetadata(
            filename=row.filename,
            title=row.title,
            artist=row.artist,
            album_artist=row.album_artist,
            album=row.album,
            genre=row.genre,
            year=row.year,
            grouping=row.grouping,
            comment=row.comment,
            tag_bpm=row.tag_bpm,
            tag_initial_key=row.tag_key,
        ),
        format=AudioFormat(
            duration_seconds=row.duration,
            codec=row.codec,
            container=row.container,
            lossless=row.lossless,
            bit_depth=row.bit_depth,
            sample_rate=row.sample_rate,
            bitrate=row.bitrate,
        ),
        quality_status=row.quality_status,
        duplicate_members=row.group_size,
        analysis=AnalysisDetails(
            status=cast(AnalysisStatus, row.analysis_status),
            confidence=row.analysis_confidence,
            bpm=_number(payload.get("bpm")),
            bpm_confidence=_number(payload.get("bpm_confidence")),
            beat_stability=_number(payload.get("beat_stability")),
            key=_optional_str(payload.get("key")),
            key_confidence=_number(payload.get("key_confidence")),
            energy=energy,
            loudness_lufs=_number(payload.get("loudness_lufs")),
            true_peak_db=_number(payload.get("true_peak_db")),
            dynamic_range=_number(payload.get("dynamic_range")),
            density=density,
            spectral_centroid=_number(payload.get("spectral_centroid")),
        ),
        windows=AnalysisWindows(**windows),
        sections=sections,
        mastering=MasteringSummary(**row.mastering),
    )


def _facet(rows: list[_Row], name: str) -> FacetSummary:
    values: list[str] = []
    for row in rows:
        value = (
            row.quality_status
            if name == "quality_status"
            else row.analysis_status
            if name == "analysis_status"
            else _optional_str(getattr(row, name, None))
        )
        if value is not None:
            values.append(value)
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    top = ordered[:50]
    return FacetSummary(
        values=tuple(FacetValue(value=value, count=count) for value, count in top),
        other_count=sum(count for _, count in ordered[50:]),
    )


def _encode_cursor(track_id: int, filters: SearchFilters, limit: int) -> str:
    payload = {
        "v": 1,
        "after_track_id": track_id,
        "query_fingerprint": _filter_fingerprint(filters, limit),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str, filters: SearchFilters, limit: int) -> int:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(raw)
        if set(payload) != {"v", "after_track_id", "query_fingerprint"} or payload["v"] != 1:
            raise ValueError
        if not isinstance(payload["after_track_id"], int) or payload["after_track_id"] < 0:
            raise ValueError
        if payload["query_fingerprint"] != _filter_fingerprint(filters, limit):
            raise ValueError
        return payload["after_track_id"]
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise CurationCatalogError("cursor is invalid or does not match these filters") from None


def _filter_fingerprint(filters: SearchFilters, limit: int) -> str:
    raw = json.dumps(
        {"filters": filters.model_dump(mode="json"), "limit": limit},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _json_object(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        raise CurationCatalogError("catalog contains invalid persisted analysis data") from None
    if not isinstance(parsed, dict):
        raise CurationCatalogError("catalog contains invalid persisted analysis data")
    return parsed


def _public_analysis_status(value: str) -> str:
    return "ok" if value in {"succeeded", "ok"} else "failed" if value == "failed" else "missing"


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_float(value: object) -> float | None:
    try:
        return None if value is None else float(cast(str | float | int, value))
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    try:
        return None if value is None else int(cast(str | float | int, value))
    except (TypeError, ValueError):
        return None


def _number(value: object) -> float | None:
    return _optional_float(value)


def _year(value: str) -> int:
    try:
        return int(value[:4])
    except ValueError:
        return -1
