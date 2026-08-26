from io import StringIO

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


def test_rich_progress_renders_offsets_and_eta_in_one_live_area() -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)
    reporter = RichProgressReporter(console=console)

    with reporter:
        reporter.phase_started("analysis", 2, 4)
        reporter.analysis_started(total=3, completed=1)
        reporter.analysis_advanced()
        reporter.analysis_finished()
        reporter.phase_finished("analysis", 3, 4)

    rendered = output.getvalue()
    assert "2/4" in rendered
    assert "1/3" in rendered or "2/3" in rendered
    assert "ETA" in rendered
    assert "\r" in rendered


def test_rich_progress_is_silent_on_a_non_interactive_console() -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=120)

    with RichProgressReporter(console=console) as reporter:
        reporter.phase_started("scan", 0, 4)
        reporter.phase_finished("scan", 1, 4)

    assert output.getvalue() == ""


def test_diagnostics_filter_and_render_on_dedicated_interactive_lines() -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)
    with RichProgressReporter(console=console, verbosity=2) as reporter:
        reporter.diagnostic("error", "broken track")
        reporter.diagnostic("warning", "slow decoder")
        reporter.diagnostic("info", "tempo ready")

    rendered = output.getvalue()
    assert "ERROR: broken track" in rendered
    assert "WARNING: slow decoder" in rendered
    assert "INFO: tempo ready" in rendered


def test_diagnostics_are_plain_filtered_lines_on_noninteractive_console() -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=120)
    reporter = RichProgressReporter(console=console, verbosity=1)
    reporter.diagnostic("error", "broken track")
    reporter.diagnostic("warning", "slow decoder")
    reporter.diagnostic("info", "hidden")

    assert output.getvalue().splitlines() == ["ERROR: broken track", "WARNING: slow decoder"]
