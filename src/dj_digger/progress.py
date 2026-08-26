"""Semantic progress reporting contracts for long-running commands."""

from typing import Protocol


class ProgressReporter(Protocol):
    """Receive progress events without depending on a presentation library."""

    def phase_started(self, name: str, completed: int, total: int) -> None: ...

    def phase_finished(self, name: str, completed: int, total: int) -> None: ...

    def analysis_started(self, *, total: int, completed: int) -> None: ...

    def analysis_advanced(self) -> None: ...

    def analysis_finished(self) -> None: ...

    def diagnostic(self, level: str, message: str) -> None: ...


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
