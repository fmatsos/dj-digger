import csv
import re
from pathlib import Path

REFERENCE = Path("skills/electronic-dj-set-curator/references/compatibility-engine.md")
TRACKS_FIXTURE = Path("tests/fixtures/tracks.tsv")


def documented_candidate_contract() -> dict[str, object]:
    assert REFERENCE.exists(), "the compatibility-engine candidate contract must exist"
    text = REFERENCE.read_text(encoding="utf-8")
    match = re.search(r"```python candidate-contract\n(.*?)\n```", text, re.DOTALL)
    assert match is not None, "the candidate contract pseudocode must be executable"
    namespace: dict[str, object] = {}
    exec(match.group(1), namespace)
    return namespace


def test_same_relative_path_in_two_sources_is_not_same_candidate() -> None:
    contract = documented_candidate_contract()
    candidate = contract["Candidate"]
    candidate_key = contract["candidate_key"]

    a = candidate(source_id="djing", track_id=1, path="Acid/A.flac")
    b = candidate(source_id="archive", track_id=9, path="Acid/A.flac")

    assert candidate_key(a) != candidate_key(b)


def test_golden_candidate_resolves_source_aware_tracks_export_row() -> None:
    contract = documented_candidate_contract()
    candidate = contract["Candidate"]
    candidate_key = contract["candidate_key"]

    with TRACKS_FIXTURE.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle, delimiter="\t"))

    assert row["set_eligible"] == "true"
    resolved = candidate(
        source_id=row["source_id"], track_id=int(row["track_id"]), path=row["path"]
    )

    assert candidate_key(resolved) == ("djing", 1)
    assert resolved.path == "Techno/Fixture.flac"
