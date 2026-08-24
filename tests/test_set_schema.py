import copy
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

SCHEMA_PATH = Path("schemas/dj-set.schema.json")
EMISSION_REFERENCE = Path("skills/electronic-dj-set-curator/references/set-emission.md")


def fixture_set() -> dict[str, object]:
    return {
        "schema_version": 2,
        "identity": "acid-rave-core",
        "series": "Acid Rave",
        "set_name": "Core",
        "brief": {
            "target_duration_minutes": 60,
            "hard": ["available"],
            "mixability": ["verified"],
            "narrative": ["build"],
        },
        "tracks": [
            {
                "position": 1,
                "source_id": "djing",
                "track_id": 42,
                "path": "Acid/Track.flac",
                "role": "opener",
                "source_quality": "lossless",
                "analysis_confidence": 1.0,
                "mixability_status": "verified",
            }
        ],
        "transitions": [],
        "alternatives": [],
        "validation": {
            "core_tracks": 1,
            "alternative_tracks": 0,
            "availability_verified": 1,
            "analysis_available": 1,
            "lossless_tracks": 1,
            "core_transitions_validated": 0,
            "lowest_transition_compatibility": None,
            "unverified_transitions": 0,
            "hard_constraints_violated": 0,
        },
    }


def validate_set(payload: dict[str, object]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)

    assert EMISSION_REFERENCE.exists(), "the source-aware set emission reference must exist"
    text = EMISSION_REFERENCE.read_text(encoding="utf-8")
    match = re.search(r"```python set-validation\n(.*?)\n```", text, re.DOTALL)
    assert match is not None, "the set validation contract pseudocode must be executable"
    namespace: dict[str, object] = {}
    exec(match.group(1), namespace)
    namespace["validate_path_references"](payload)


def test_set_track_requires_source_identity() -> None:
    payload = fixture_set()
    del payload["tracks"][0]["source_id"]  # type: ignore[index]

    with pytest.raises(ValidationError):
        validate_set(payload)


def test_set_alternative_requires_source_identity() -> None:
    payload = fixture_set()
    payload["alternatives"] = [
        {
            "source_id": "djing",
            "track_id": 43,
            "path": "Acid/Alternative.flac",
            "role": "alternative",
            "replace_position": 1,
            "entry_from_path": None,
            "entry_compatibility": None,
            "entry_strategy": None,
            "rejoin_to_path": None,
            "exit_compatibility": None,
            "exit_strategy": None,
        }
    ]
    del payload["alternatives"][0]["source_id"]  # type: ignore[index]

    with pytest.raises(ValidationError):
        validate_set(payload)


def test_set_rejects_transition_path_ambiguous_across_sources() -> None:
    payload = fixture_set()
    duplicate = copy.deepcopy(payload["tracks"][0])  # type: ignore[index]
    duplicate.update({"position": 2, "source_id": "archive", "track_id": 9})
    payload["tracks"].append(duplicate)  # type: ignore[index]
    payload["transitions"] = [
        {
            "from_path": "Acid/Track.flac",
            "to_path": "Acid/Track.flac",
            "compatibility": 1.0,
            "confidence": "HIGH",
            "strategy": "STANDARD_BLEND",
            "overlap_bars": 16,
            "outgoing_region": "outro",
            "incoming_region": "intro",
            "target_bpm": 130,
            "from_pitch_percent": 0,
            "to_pitch_percent": 0,
            "bass_handoff": "swap",
            "reasons": ["fixture"],
        }
    ]

    with pytest.raises(ValidationError, match="ambiguous"):
        validate_set(payload)
