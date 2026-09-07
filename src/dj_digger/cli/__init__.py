"""Public command-line entry point."""

from dj_digger.cli import background
from dj_digger.cli.app import _run, app, main
from dj_digger.core.application import CoreApplication
from dj_digger.core.config import WorkspaceConfig
from dj_digger.logging import RunLogger
from dj_digger.rich_progress import RichProgressReporter

WorkspaceApplication = CoreApplication

__all__ = [
    "CoreApplication",
    "RunLogger",
    "RichProgressReporter",
    "WorkspaceApplication",
    "WorkspaceConfig",
    "_run",
    "app",
    "background",
    "main",
]
