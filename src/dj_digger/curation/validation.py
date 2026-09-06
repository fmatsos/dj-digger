"""Validation for packaged, versioned curation result contracts."""

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any

from jsonschema import (  # type: ignore[import-untyped]
    Draft202012Validator,
    FormatChecker,
    ValidationError,
)

_CURRENT_SCHEMA_ID = "https://dj-digger.local/schemas/v1/curation-result.schema.json"


def _load_schema(name: str) -> dict[str, Any]:
    resource = files("dj_digger").joinpath("schemas", name)
    if not resource.is_file():
        raise FileNotFoundError(f"required packaged resource missing: dj_digger/schemas/{name}")
    value: object = json.loads(resource.read_text(encoding="utf-8"))
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

    identities = [_identity(track["identity"]) for track in tracks]
    if len(identities) != len(set(identities)):
        raise ValidationError("duplicate canonical track identity is ambiguous")
    known = set(identities)
    for transition in transitions:
        for endpoint in ("from", "to"):
            if _identity(transition[endpoint]) not in known:
                raise ValidationError(f"transition {endpoint} does not reference a canonical track")


def validate_curation_result(payload: Mapping[str, object]) -> None:
    """Validate a current result or the explicitly supported historical set V2."""
    if payload.get("schema_version") == 2 and "schema_id" not in payload:
        Draft202012Validator(_load_schema("dj-set.schema.json")).validate(payload)
        return
    if payload.get("schema_id") != _CURRENT_SCHEMA_ID:
        raise ValidationError("unsupported curation result schema identifier")
    _validate_current(payload)
