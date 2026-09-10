"""Progress ports emitted by the domain and adapted by the outer layers.

These are ports, not use cases: the analysis pipeline and the duplicate
service report through them, so they must live where the domain can reach
them without depending on the application layer above it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProgressEvent:
    """One framework-independent progress update."""

    kind: str
    completed: int | None
    total: int | None
    subject: str | None


ProgressSink = Callable[[ProgressEvent], None]


class ProgressReporter(Protocol):
    """Receive progress events without depending on a presentation library."""

    def phase_started(self, name: str, completed: int, total: int) -> None: ...

    def phase_finished(self, name: str, completed: int, total: int) -> None: ...

    def analysis_started(self, *, total: int, completed: int) -> None: ...

    def analysis_advanced(self) -> None: ...

    def analysis_finished(self) -> None: ...

    def diagnostic(self, level: str, message: str) -> None: ...


AnalysisProgressReporter = ProgressReporter


class ProgressEventReporter:
    """Translate legacy analysis callbacks into presentation-neutral events."""

    def __init__(self, sink: ProgressSink) -> None:
        self._sink = sink

    def phase_started(self, name: str, completed: int, total: int) -> None:
        self._emit("phase_started", completed, total, name)

    def phase_finished(self, name: str, completed: int, total: int) -> None:
        self._emit("phase_finished", completed, total, name)

    def analysis_started(self, *, total: int, completed: int) -> None:
        self._emit("analysis_started", completed, total, None)

    def analysis_advanced(self) -> None:
        self._emit("analysis_advanced", None, None, None)

    def analysis_finished(self) -> None:
        self._emit("analysis_finished", None, None, None)

    def diagnostic(self, level: str, message: str) -> None:
        self._emit("diagnostic", None, None, f"{level}:{message}")

    def _emit(
        self, kind: str, completed: int | None, total: int | None, subject: str | None
    ) -> None:
        self._sink(ProgressEvent(kind, completed, total, subject))


class NullProgressReporter:
    """Discard progress events for programmatic and non-instrumented callers."""

    def phase_started(self, name: str, completed: int, total: int) -> None:
        pass

    def phase_finished(self, name: str, completed: int, total: int) -> None:
        pass

    def analysis_started(self, *, total: int, completed: int) -> None:
        pass

    def analysis_advanced(self) -> None:
        pass

    def analysis_finished(self) -> None:
        pass

    def diagnostic(self, level: str, message: str) -> None:
        pass


__all__ = [
    "AnalysisProgressReporter",
    "NullProgressReporter",
    "ProgressEvent",
    "ProgressEventReporter",
    "ProgressReporter",
    "ProgressSink",
]
