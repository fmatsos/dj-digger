"""Deterministic best-quality selection per duplicate group and source."""

from dataclasses import dataclass

from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.duplicates.fingerprint import FINGERPRINT_VERSION
from dj_digger.duplicates.repository import DuplicateRepository

RANKING_VERSION = "quality-rank/1"


@dataclass(frozen=True)
class TechnicalFacts:
    """Current quality-relevant facts for one track's technical probe."""

    lossless: bool | None
    bit_depth: int | None
    sample_rate: int | None
    bitrate: int | None


@dataclass(frozen=True)
class QualityMarkResult:
    """Outcome of one best-quality marking pass."""

    status: str
    marked_best: int
    incomplete_track_ids: tuple[int, ...] = ()


def _rank_key(track: Track, facts: TechnicalFacts) -> tuple[int, int, int, str]:
    """Lower sorts first: known lossless, then lossy, then unknown; ties broken by path."""
    if facts.lossless is True:
        return (0, -(facts.bit_depth or -1), -(facts.sample_rate or -1), track.relative_path)
    if facts.lossless is False:
        return (1, -(facts.bitrate or -1), -(facts.sample_rate or -1), track.relative_path)
    return (2, 0, 0, track.relative_path)


class QualitySelector:
    """Elect the best-quality present track per (source, fingerprint_hash) group."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._repository = DuplicateRepository(database)

    def mark_best_quality(self, source_id: str | None = None) -> QualityMarkResult:
        """Replace quality selections for the requested scope, or refuse if incomplete."""
        present = self._repository.present_tracks(source_id)
        source_ids = (
            {source_id} if source_id is not None else {track.source_id for track in present}
        )

        facts_by_track: dict[int, TechnicalFacts] = {}
        incomplete: list[int] = []
        for track in present:
            facts = self._current_facts(track)
            if facts is None:
                incomplete.append(track.id)
            else:
                facts_by_track[track.id] = facts
        if incomplete:
            return QualityMarkResult(
                status="failed", marked_best=0, incomplete_track_ids=tuple(sorted(incomplete))
            )

        groups = self._repository.groups(source_id)
        marked_total = 0
        with self._database.transaction():
            for scoped_source_id in sorted(source_ids):
                selections: dict[str, int] = {}
                for group in groups:
                    members = [m for m in group.members if m.source_id == scoped_source_id]
                    if len(members) < 2:
                        continue
                    winner = min(
                        members, key=lambda m: _rank_key(m.track, facts_by_track[m.track.id])
                    )
                    selections[group.fingerprint_hash] = winner.track.id
                self._repository.replace_quality_selections(
                    scoped_source_id, selections, RANKING_VERSION
                )
                marked_total += len(selections)
        return QualityMarkResult(status="succeeded", marked_best=marked_total)

    def _current_facts(self, track: Track) -> TechnicalFacts | None:
        has_current_fingerprint = (
            self._repository.reusable_fingerprint(track, FINGERPRINT_VERSION) is not None
        )
        if not has_current_fingerprint:
            return None
        row = self._database.execute(
            """
            SELECT lossless, bit_depth, sample_rate, bitrate
            FROM technical_audio_metadata
            WHERE track_id = ? AND input_size_bytes = ? AND input_mtime_ns = ?
            """,
            (track.id, track.size_bytes, track.mtime_ns),
        ).fetchone()
        if row is None:
            return None
        lossless, bit_depth, sample_rate, bitrate = row
        return TechnicalFacts(
            lossless=None if lossless is None else bool(lossless),
            bit_depth=bit_depth,
            sample_rate=sample_rate,
            bitrate=bitrate,
        )
