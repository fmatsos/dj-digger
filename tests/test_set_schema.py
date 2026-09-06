import copy

import pytest
from jsonschema import ValidationError

from dj_digger.curation.validation import validate_curation_result


def fixture_result() -> dict[str, object]:
    return {
        "schema_version": 1,
        "schema_id": "https://dj-digger.local/schemas/v1/curation-result.schema.json",
        "type": "set",
        "status": "draft",
        "identity": "curation-fixture-001",
        "prompt": "Build a coherent one-hour set.",
        "tracks": [
            {
                "position": 1,
                "identity": {"source_id": "fixture", "track_id": 42},
                "role": "opener",
            },
            {
                "position": 2,
                "identity": {"source_id": "fixture", "track_id": 43},
                "role": "closer",
            },
        ],
        "transitions": [
            {
                "from": {"source_id": "fixture", "track_id": 42},
                "to": {"source_id": "fixture", "track_id": 43},
                "explanation": "A general mixing suggestion, not a catalog fact.",
            }
        ],
        "warnings": [],
        "report": {
            "summary": "A compact fixture result.",
            "attested_facts": [
                {
                    "statement": "Both selections are available.",
                    "evidence": [
                        {"source": "dj_digger", "fact": "availability", "track_positions": [1, 2]}
                    ],
                }
            ],
            "llm_explanations": ["The ordering should create a broad narrative arc."],
        },
        "provenance": {
            "generator": "dj-digger",
            "model": "fixture-model",
            "generated_at": "2026-01-01T00:00:00Z",
            "catalog_snapshot": "fixture-snapshot",
        },
    }


def fixture_legacy_set() -> dict[str, object]:
    return {
        "schema_version": 2,
        "identity": "legacy-fixture",
        "series": "Fixture Series",
        "set_name": "Fixture Set",
        "brief": {
            "target_duration_minutes": 60,
            "hard": ["available"],
            "mixability": ["verified"],
            "narrative": ["build"],
        },
        "tracks": [
            {
                "position": 1,
                "source_id": "fixture",
                "track_id": 42,
                "path": "Fixture/Track.flac",
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


def fixture_legacy_transition() -> dict[str, object]:
    return {
        "from_path": "Fixture/Track.flac",
        "to_path": "Fixture/Track.flac",
        "compatibility": 0.8,
        "confidence": "HIGH",
        "strategy": "STANDARD_BLEND",
        "overlap_bars": 16,
        "outgoing_region": "outro",
        "incoming_region": "intro",
        "target_bpm": 128,
        "from_pitch_percent": 0,
        "to_pitch_percent": 0,
        "bass_handoff": "midpoint",
        "reasons": ["fixture"],
    }


def test_curation_result_accepts_the_current_contract() -> None:
    validate_curation_result(fixture_result())


def test_curation_result_rejects_nonexistent_transition_reference() -> None:
    payload = fixture_result()
    payload["transitions"][0]["to"]["track_id"] = 99  # type: ignore[index]

    with pytest.raises(ValidationError, match="does not reference a canonical track"):
        validate_curation_result(payload)


def test_curation_result_rejects_nonexistent_evidence_track_position() -> None:
    payload = fixture_result()
    payload["report"]["attested_facts"][0]["evidence"][0]["track_positions"] = [99]  # type: ignore[index]

    with pytest.raises(
        ValidationError, match="evidence does not reference a canonical track position"
    ):
        validate_curation_result(payload)


def test_curation_result_rejects_ambiguous_stable_identity() -> None:
    payload = fixture_result()
    payload["tracks"][1]["identity"] = copy.deepcopy(  # type: ignore[index]
        payload["tracks"][0]["identity"]  # type: ignore[index]
    )

    with pytest.raises(ValidationError, match="duplicate canonical track identity"):
        validate_curation_result(payload)


def test_curation_result_rejects_non_contiguous_positions() -> None:
    payload = fixture_result()
    payload["tracks"][1]["position"] = 3  # type: ignore[index]

    with pytest.raises(ValidationError, match="positions must be continuous"):
        validate_curation_result(payload)


def test_curation_result_rejects_invalid_status() -> None:
    payload = fixture_result()
    payload["status"] = "unknown"

    with pytest.raises(ValidationError):
        validate_curation_result(payload)


def test_curation_result_requires_report() -> None:
    payload = fixture_result()
    del payload["report"]

    with pytest.raises(ValidationError):
        validate_curation_result(payload)


def test_curation_result_rejects_unsourced_attested_fact() -> None:
    payload = fixture_result()
    payload["report"]["attested_facts"][0]["evidence"] = []  # type: ignore[index]

    with pytest.raises(ValidationError):
        validate_curation_result(payload)


def test_historical_dj_set_v2_remains_compatible() -> None:
    validate_curation_result(fixture_legacy_set())


def test_historical_dj_set_v2_rejects_missing_transition_path() -> None:
    payload = fixture_legacy_set()
    transition = fixture_legacy_transition()
    transition["to_path"] = "Fixture/Missing.flac"
    payload["transitions"] = [transition]

    with pytest.raises(ValidationError, match="ambiguous or does not resolve"):
        validate_curation_result(payload)


def test_historical_dj_set_v2_rejects_ambiguous_transition_path() -> None:
    payload = fixture_legacy_set()
    duplicate_path_track = copy.deepcopy(payload["tracks"][0])  # type: ignore[index]
    duplicate_path_track.update({"position": 2, "source_id": "second-source", "track_id": 43})
    payload["tracks"].append(duplicate_path_track)  # type: ignore[union-attr]
    payload["transitions"] = [fixture_legacy_transition()]

    with pytest.raises(ValidationError, match="ambiguous or does not resolve"):
        validate_curation_result(payload)
