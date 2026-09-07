"""Public result value for bounded duplicate-group mastering analysis."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MasteringAnalysisResult:
    """Counters from one mastering phase."""

    files_total: int
    analyzed: int
    reused: int
    failed: int

    @property
    def status(self) -> str:
        return "partial" if self.failed else "succeeded"
