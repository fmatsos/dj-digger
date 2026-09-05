"""Small, wording-tolerant helpers for SQLite query-plan assertions."""

import re

from dj_digger.catalog.database import Database

_SCAN = re.compile(r"^\s*SCAN\s+(?P<table>\S+)", re.IGNORECASE)


def explain(database: Database, sql: str, parameters: tuple[object, ...] = ()) -> list[str]:
    """Return only normalized detail strings from ``EXPLAIN QUERY PLAN``."""
    return [
        str(row[3]).strip() for row in database.execute(f"EXPLAIN QUERY PLAN {sql}", parameters)
    ]


def has_full_scan(details: list[str], table: str) -> bool:
    """Return whether SQLite reports a top-level table scan for ``table``."""
    expected = _normalize_identifier(table)
    for detail in details:
        match = _SCAN.match(detail)
        if match is not None and _normalize_identifier(match.group("table")) == expected:
            return True
    return False


def _normalize_identifier(identifier: str) -> str:
    return identifier.rsplit(".", maxsplit=1)[-1].strip('"`[]').casefold()
