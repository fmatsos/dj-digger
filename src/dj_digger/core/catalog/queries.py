"""Shared building blocks for catalog track queries.

The scope predicate and its LIKE escaping used to be re-implemented in four
places. Escaping is subtle enough that four copies means a fix lands in one.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from dj_digger.core.catalog.models import PresenceStatus, Track

#: Column list every ``Track`` row is built from, in ``Track`` field order.
TRACK_COLUMNS = (
    "t.id, t.source_id, t.relative_path, t.filename, t.extension, t.size_bytes, "
    "t.mtime_ns, t.presence_status"
)
#: Deterministic order so limits and pagination stay reproducible.
TRACK_ORDER = " ORDER BY t.source_id, t.relative_path, t.id"

_LIKE_ESCAPE = "\\"


def escape_like_prefix(prefix: str) -> str:
    """Escape LIKE wildcards so a path prefix matches literally.

    The escape character itself is escaped first; doing it later would
    double-escape the backslashes introduced for ``%`` and ``_``.
    """
    return (
        prefix.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )


@dataclass(frozen=True)
class TrackScope:
    """Optional narrowing of a track query to one source and/or path prefix."""

    source_id: str | None = None
    path_prefix: str | None = None

    def as_sql(self, alias: str = "t") -> tuple[str, list[object]]:
        """Return the extra predicate and its bound parameters."""
        clause = ""
        parameters: list[object] = []
        if self.source_id is not None:
            clause += f" AND {alias}.source_id = ?"
            parameters.append(self.source_id)
        if self.path_prefix is not None:
            clause += f" AND {alias}.relative_path LIKE ? ESCAPE '{_LIKE_ESCAPE}'"
            parameters.append(f"{escape_like_prefix(self.path_prefix)}%")
        return clause, parameters


def track_from_row(row: Sequence[Any]) -> Track:
    """Build a Track from a row selected with ``TRACK_COLUMNS``.

    Keeping the mapper next to the column list is what makes the positional
    decode safe: reordering one without the other is a single-file edit.
    """
    return Track(
        id=int(row[0]),
        source_id=str(row[1]),
        relative_path=str(row[2]),
        filename=str(row[3]),
        extension=str(row[4]),
        size_bytes=int(row[5]),
        mtime_ns=int(row[6]),
        presence_status=PresenceStatus(row[7]),
    )


__all__ = [
    "TRACK_COLUMNS",
    "TRACK_ORDER",
    "TrackScope",
    "escape_like_prefix",
    "track_from_row",
]
