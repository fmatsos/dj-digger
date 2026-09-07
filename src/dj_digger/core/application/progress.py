"""Generic progress events emitted by core use cases."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressEvent:
    """One framework-independent progress update."""

    kind: str
    completed: int | None
    total: int | None
    subject: str | None


ProgressSink = Callable[[ProgressEvent], None]
