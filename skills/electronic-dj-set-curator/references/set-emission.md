# Set emission contract (V2)

Machine-readable `.set.json` artifacts use schema version `2`. Every selected
track and every alternative carries its stable source-aware identity:

```json
{"position":1,"source_id":"djing","track_id":42,"path":"Acid/Track.flac","role":"opener"}
```

`path` remains source-relative and is retained in transition fields for human
readability. Before publishing an artifact, references from transitions and
alternative entry/rejoin links must resolve to exactly one selected track path.
An identical path in separate sources is therefore not silently chosen.

```python set-validation
from collections import defaultdict

from jsonschema import ValidationError


def validate_path_references(payload: dict[str, object]) -> None:
    sources_by_path: dict[str, set[str]] = defaultdict(set)
    for track in payload["tracks"]:
        sources_by_path[track["path"]].add(track["source_id"])

    references: list[tuple[str, str]] = []
    for transition in payload["transitions"]:
        references.extend(
            (("from_path", transition["from_path"]), ("to_path", transition["to_path"]))
        )
    for alternative in payload["alternatives"]:
        for field in ("entry_from_path", "rejoin_to_path"):
            if alternative[field] is not None:
                references.append((field, alternative[field]))

    for field, path in references:
        sources = sources_by_path[path]
        if len(sources) != 1:
            raise ValidationError(
                f"{field} path {path!r} is ambiguous or does not resolve to a selected track"
            )
```
