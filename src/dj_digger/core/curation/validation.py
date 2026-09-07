"""Validation for packaged, versioned curation result contracts."""

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from jsonschema import (  # type: ignore[import-untyped]
    Draft202012Validator,
    FormatChecker,
    ValidationError,
)

from dj_digger.core.resources import read_text

_CURRENT_SCHEMA_ID = "https://dj-digger.local/schemas/v1/curation-result.schema.json"


def _load_schema(name: str) -> dict[str, Any]:
    value: object = json.loads(read_text(f"core/schemas/{name}"))
    if not isinstance(value, dict):
        raise RuntimeError(f"packaged schema is not an object: {name}")
    return value


def _identity(value: object) -> tuple[str, int]:
    if not isinstance(value, Mapping):
        raise ValidationError("track identity must be an object")
    source_id = value.get("source_id")
    track_id = value.get("track_id")
    if not isinstance(source_id, str) or not isinstance(track_id, int):
        raise ValidationError("track identity is invalid")
    return source_id, track_id


def _validate_current(payload: Mapping[str, object]) -> None:
    schema = _load_schema("curation-result.schema.json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)

    tracks = payload["tracks"]
    transitions = payload["transitions"]
    assert isinstance(tracks, list)
    assert isinstance(transitions, list)
    positions = [track["position"] for track in tracks]
    if positions != list(range(1, len(tracks) + 1)):
        raise ValidationError("canonical track positions must be continuous and ordered from 1")

    report = payload["report"]
    assert isinstance(report, Mapping)
    attested_facts = report["attested_facts"]
    assert isinstance(attested_facts, list)
    known_positions = set(positions)
    for attested_fact in attested_facts:
        for evidence in attested_fact["evidence"]:
            if not set(evidence["track_positions"]).issubset(known_positions):
                raise ValidationError("evidence does not reference a canonical track position")

    identities = [_identity(track["identity"]) for track in tracks]
    if len(identities) != len(set(identities)):
        raise ValidationError("duplicate canonical track identity is ambiguous")
    known = set(identities)
    for transition in transitions:
        for endpoint in ("from", "to"):
            if _identity(transition[endpoint]) not in known:
                raise ValidationError(f"transition {endpoint} does not reference a canonical track")


def _validate_legacy_path_references(payload: Mapping[str, object]) -> None:
    tracks = payload["tracks"]
    transitions = payload["transitions"]
    alternatives = payload["alternatives"]
    assert isinstance(tracks, list)
    assert isinstance(transitions, list)
    assert isinstance(alternatives, list)

    sources_by_path: dict[str, set[str]] = defaultdict(set)
    for track in tracks:
        sources_by_path[track["path"]].add(track["source_id"])

    references: list[tuple[str, str]] = []
    for transition in transitions:
        references.extend(
            (("from_path", transition["from_path"]), ("to_path", transition["to_path"]))
        )
    for alternative in alternatives:
        for field in ("entry_from_path", "rejoin_to_path"):
            path = alternative[field]
            if path is not None:
                references.append((field, path))

    for field, path in references:
        if len(sources_by_path[path]) != 1:
            raise ValidationError(
                f"{field} path {path!r} is ambiguous or does not resolve to a selected track"
            )


def validate_curation_result(payload: Mapping[str, object]) -> None:
    """Validate a current result or the explicitly supported historical set V2."""
    if payload.get("schema_version") == 2 and "schema_id" not in payload:
        Draft202012Validator(_load_schema("dj-set.schema.json")).validate(payload)
        _validate_legacy_path_references(payload)
        return
    if payload.get("schema_id") != _CURRENT_SCHEMA_ID:
        raise ValidationError("unsupported curation result schema identifier")
    _validate_current(payload)
