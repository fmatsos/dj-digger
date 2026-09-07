"""Public command-line entry point."""

from dj_digger import background
from dj_digger.application import WorkspaceApplication
from dj_digger.cli.app import (
    _run,
    app,
    main,
)
from dj_digger.core.config import WorkspaceConfig
from dj_digger.logging import RunLogger
from dj_digger.rich_progress import RichProgressReporter

__all__ = [
    "RunLogger",
    "RichProgressReporter",
    "WorkspaceApplication",
    "WorkspaceConfig",
    "_run",
    "app",
    "background",
    "main",
]
