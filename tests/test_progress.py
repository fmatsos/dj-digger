from rich.console import Console

from dj_digger.progress import NullProgressReporter
from dj_digger.rich_progress import RichProgressReporter


def test_null_progress_reporter_accepts_the_complete_lifecycle() -> None:
    reporter = NullProgressReporter()

    reporter.phase_started("scan", 0, 4)
    reporter.phase_finished("scan", 1, 4)
    reporter.analysis_started(total=3, completed=1)
    reporter.analysis_advanced()
    reporter.analysis_finished()


def test_rich_progress_accepts_the_complete_lifecycle() -> None:
    console = Console(force_terminal=False)
    reporter = RichProgressReporter(console=console)

    with reporter:
        reporter.phase_started("analysis", 2, 4)
        reporter.analysis_started(total=3, completed=1)
        reporter.analysis_advanced()
        reporter.analysis_finished()
        reporter.phase_finished("analysis", 3, 4)


def test_rich_progress_accepts_filtered_diagnostics_without_render_assertions() -> None:
    reporter = RichProgressReporter(console=Console(force_terminal=False), verbosity=1)
    reporter.diagnostic("error", "broken track")
    reporter.diagnostic("warning", "slow decoder")
    reporter.diagnostic("info", "hidden")
