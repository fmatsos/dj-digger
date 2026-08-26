"""Rich terminal adapter for refresh progress events."""

from types import TracebackType

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.text import Text


class _TrackSpeedColumn(ProgressColumn):
    def render(self, task: Task) -> Text:
        if task.fields.get("kind") != "analysis" or task.speed is None:
            return Text("")
        return Text(f"{task.speed:.1f} morceau/s")


class RichProgressReporter:
    """Render semantic progress events in one transient live terminal area."""

    def __init__(self, *, console: Console | None = None, verbosity: int = 0) -> None:
        self._console = console or Console(stderr=True)
        self._enabled = self._console.is_terminal
        self._verbosity = max(0, min(2, verbosity))
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            _TrackSpeedColumn(),
            TextColumn("ETA"),
            TimeRemainingColumn(),
            console=self._console,
            transient=True,
            disable=not self._enabled,
            redirect_stdout=False,
            redirect_stderr=False,
        )
        self._phase_task = self._progress.add_task("Refresh", total=4, kind="phase")
        self._analysis_task: TaskID | None = None

    def __enter__(self) -> "RichProgressReporter":
        if self._enabled:
            self._progress.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._enabled:
            self._progress.stop()

    def phase_started(self, name: str, completed: int, total: int) -> None:
        if name == "analysis":
            self.diagnostic("info", "tempo analysis and beat-grid extraction started")
        self._progress.update(
            self._phase_task,
            description=f"Refresh · {name.capitalize()}",
            completed=completed,
            total=total,
        )
        self._progress.refresh()

    def diagnostic(self, level: str, message: str) -> None:
        """Print a filtered diagnostic on a line separate from live progress."""
        required = {"error": 0, "warning": 1, "info": 2}.get(level.lower())
        if required is None or required > self._verbosity:
            return
        line = f"{level.upper()}: {message}"
        if self._enabled and self._progress.live.is_started:
            self._progress.live.console.print(line)
        else:
            self._console.print(line)

    def phase_finished(self, name: str, completed: int, total: int) -> None:
        self._progress.update(self._phase_task, completed=completed, total=total)
        self._progress.refresh()

    def analysis_started(self, *, total: int, completed: int) -> None:
        if self._analysis_task is not None:
            self._progress.remove_task(self._analysis_task)
        self._analysis_task = self._progress.add_task(
            "Analyse", total=total, completed=completed, kind="analysis"
        )
        self._progress.refresh()

    def analysis_advanced(self) -> None:
        if self._analysis_task is not None:
            self._progress.advance(self._analysis_task)
            self._progress.refresh()

    def analysis_finished(self) -> None:
        if self._analysis_task is not None:
            self._progress.remove_task(self._analysis_task)
            self._analysis_task = None
            self._progress.refresh()
