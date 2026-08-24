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

## M3U8 set-copy contract

An M3U8 is a set-copy list, not an inventory export. Emit each selected track's
exact source-relative `path` verbatim: never convert it to an absolute path and
never prefix it with `source_id`.

The default M3U8 mode is single-source. If selected tracks span sources, the
caller must supply an explicitly resolvable `common_library_root`.
That root authorizes the external set-copy workflow but is not written into the
playlist; the M3U8 still contains only exact relative paths.

```python playlist-emission
from collections.abc import Iterable, Mapping


class AmbiguousLibraryRoot(ValueError):
    def __init__(self, source_ids: set[str]) -> None:
        self.source_ids = source_ids
        super().__init__(f"M3U8 spans source ids without a common library root: {sorted(source_ids)}")


def emit_m3u8(
    tracks: Iterable[Mapping[str, str]], common_library_root: str | None = None
) -> str:
    selected_tracks = list(tracks)
    source_ids = {track["source_id"] for track in selected_tracks}
    if len(source_ids) != 1 and common_library_root is None:
        raise AmbiguousLibraryRoot(source_ids)
    return "#EXTM3U\n" + "\n".join(track["path"] for track in selected_tracks) + "\n"
```

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
