# Compatibility engine

## Source-aware candidate identity (V1A)

`Candidate` identity is source-aware. Its internal key is the pair
`(source_id, track_id)`; `path` remains the source-relative display and
filesystem contract. In particular, `path` must not be used as a candidate
identity, lookup, de-duplication, or cache key.

```python candidate-contract
from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    source_id: str
    track_id: int
    path: str


def candidate_key(c: Candidate) -> tuple[str, int]:
    return (c.source_id, c.track_id)
```

### Fixture

| source_id | track_id | path | candidate_key |
| --- | ---: | --- | --- |
| `djing` | 1 | `Acid/A.flac` | `("djing", 1)` |
| `archive` | 9 | `Acid/A.flac` | `("archive", 9)` |

The two fixture candidates have the same path but are distinct candidates.

## Preserved compatibility behavior

This identity migration changes no compatibility behavior. The existing seven
transition-strategy enum values remain exactly the same; no strategy is added,
removed, renamed, or reinterpreted. Confidence gates and the narrative curve
remain unchanged. Hard constraints remain non-compensable: a score or another
strategy cannot override a failed hard constraint.
