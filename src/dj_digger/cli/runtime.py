"""The single execution boundary shared by every CLI command.

One place loads the workspace, composes the application, classifies failures,
persists the run log, records background results, emits the payload and maps
status to an exit code. Dependencies are passed in explicitly so tests can
substitute them without reaching into ``sys.modules``.
"""

import json
import logging
import tomllib
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol

import typer

from dj_digger.cli import background
from dj_digger.cli.rich_progress import RichProgressReporter
from dj_digger.cli.terminal import render
from dj_digger.core.application import CoreApplication
from dj_digger.core.application.progress import ProgressSink
from dj_digger.core.config import WorkspaceConfig
from dj_digger.core.diagnostics import DiagnosticStatus
from dj_digger.core.errors import classify
from dj_digger.core.run_log import RunLogger

EXIT_FAILED = 1
EXIT_PARTIAL = 2

Diagnostic = dict[str, Any]
Action = Callable[[CoreApplication], Diagnostic]
ProgressAction = Callable[[CoreApplication, ProgressSink], Diagnostic]

_logger = logging.getLogger("dj_digger")


class RunLogSink(Protocol):
    """The only run-logger capability a command boundary needs."""

    def write(self, diagnostic: Diagnostic) -> None: ...


class ApplicationFactory(Protocol):
    """How one command obtains a scoped application session."""

    def __call__(self, config: WorkspaceConfig, /) -> AbstractContextManager[Any]: ...


class LoggerFactory(Protocol):
    """How one command obtains the workspace run logger."""

    def __call__(self, database_path: Path, /) -> RunLogSink: ...


class ConfigLoadError(ValueError):
    """A workspace configuration could not be parsed or validated."""


_LEVELS = {0: logging.WARNING, 1: logging.INFO}
_stderr_handler: logging.Handler | None = None


def configure_logging(verbosity: int) -> None:
    """Route dj-digger diagnostics to stderr at the level the caller asked for.

    Only this package's logger is configured: touching the root logger would
    stomp on whatever configuration an embedding process or test harness set
    up. The run log stays the sanitized, persisted record and never carries
    the detail printed here.
    """
    global _stderr_handler
    logger = logging.getLogger("dj_digger")
    logger.setLevel(_LEVELS.get(verbosity, logging.DEBUG))
    if _stderr_handler is None:
        _stderr_handler = logging.StreamHandler()
        _stderr_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    if _stderr_handler not in logger.handlers:
        logger.addHandler(_stderr_handler)


def load_config(config_path: Path) -> WorkspaceConfig:
    """Load one workspace config with a stable, actionable CLI error."""
    try:
        return WorkspaceConfig.load(config_path)
    except (OSError, tomllib.TOMLDecodeError, ValueError) as error:
        detail = str(error).strip() or "configuration is invalid"
        raise ConfigLoadError(f"invalid configuration: {detail}") from None


def config_failure(event: str, error: ConfigLoadError) -> Diagnostic:
    return {
        "event": event,
        "status": DiagnosticStatus.FAILED,
        "code": "invalid_config",
        "error": str(error),
    }


def progress_reporter(verbosity: int) -> AbstractContextManager[ProgressSink]:
    """Build the interactive progress reporter for one command run."""
    return RichProgressReporter(verbosity=verbosity)


def emit_json(payload: Diagnostic) -> None:
    """Emit one compact machine-readable payload."""
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def emit(payload: Diagnostic, *, json_output: bool) -> None:
    """Emit one payload in the format the caller selected."""
    if json_output:
        emit_json(payload)
    else:
        render(payload)


_EXIT_CODES: dict[str, int] = {
    DiagnosticStatus.FAILED: EXIT_FAILED,
    DiagnosticStatus.PARTIAL: EXIT_PARTIAL,
}


def exit_code_for(diagnostic: Diagnostic) -> int:
    """Map one diagnostic status to the documented process exit code."""
    status = diagnostic.get("status")
    return _EXIT_CODES.get(status, 0) if isinstance(status, str) else 0


def execute_command(
    config_path: Path,
    action: Action,
    *,
    event: str,
    application_factory: ApplicationFactory = CoreApplication,
    logger_factory: LoggerFactory = RunLogger,
) -> Diagnostic:
    """Run one action against a scoped application and return its diagnostic."""
    try:
        config = load_config(config_path)
    except ConfigLoadError as error:
        # The structured diagnostic below is the user-facing channel; keep the
        # log line for troubleshooting without duplicating it on stderr.
        _logger.debug("%s: %s", event, error)
        return config_failure(event, error)
    logger = logger_factory(config.database)
    try:
        with application_factory(config) as service:
            diagnostic = action(service)
    except Exception as error:
        # The operator gets the traceback on stderr; the persisted run log only
        # ever gets the failure class, never private library detail.
        _logger.exception("%s failed", event)
        diagnostic = {
            "event": event,
            "status": DiagnosticStatus.FAILED,
            "error": str(error),
            "error_class": classify(error),
        }
    logger.write(diagnostic)
    job_id = background.current_job_id()
    if job_id is not None:
        background.record_result(config.database, job_id, diagnostic)
    return diagnostic


def run_command(
    config_path: Path,
    action: Action,
    *,
    event: str,
    json_output: bool = False,
    application_factory: ApplicationFactory = CoreApplication,
    logger_factory: LoggerFactory = RunLogger,
) -> None:
    """Execute one command end to end, emitting its payload and exit code."""
    diagnostic = execute_command(
        config_path,
        action,
        event=event,
        application_factory=application_factory,
        logger_factory=logger_factory,
    )
    emit(diagnostic, json_output=json_output)
    code = exit_code_for(diagnostic)
    if code:
        raise typer.Exit(code)


def run_command_with_progress(
    config_path: Path,
    action: ProgressAction,
    *,
    event: str,
    verbosity: int,
    json_output: bool = False,
) -> None:
    """Execute one long-running command with an interactive progress reporter.

    The reporter's lifetime is owned here, next to the catalog session's, so no
    command has to remember to close it on failure.
    """

    def with_progress(service: CoreApplication) -> Diagnostic:
        with progress_reporter(verbosity) as progress:
            return action(service, progress)

    run_command(config_path, with_progress, event=event, json_output=json_output)


def run_with_config(
    config_path: Path,
    action: Callable[[WorkspaceConfig], Diagnostic],
    *,
    event: str,
    json_output: bool = False,
) -> None:
    """Execute one command that needs the workspace config but no catalog session."""
    try:
        config = load_config(config_path)
    except ConfigLoadError as error:
        _logger.debug("%s: %s", event, error)
        emit(config_failure(event, error), json_output=json_output)
        raise typer.Exit(EXIT_FAILED) from None
    diagnostic = action(config)
    emit(diagnostic, json_output=json_output)
    code = exit_code_for(diagnostic)
    if code:
        raise typer.Exit(code)


__all__ = [
    "EXIT_FAILED",
    "EXIT_PARTIAL",
    "Action",
    "ConfigLoadError",
    "Diagnostic",
    "config_failure",
    "configure_logging",
    "emit",
    "emit_json",
    "execute_command",
    "exit_code_for",
    "load_config",
    "progress_reporter",
    "run_command",
    "run_command_with_progress",
    "run_with_config",
]
