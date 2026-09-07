"""CLI adapter for the catalog-independent portable set copy."""

from dj_digger.core.application.copy_set import CopySetRequest, CopySetUseCase
from dj_digger.core.application.progress import ProgressSink
from dj_digger.core.set_copy import SetCopyResult


def execute(
    request: CopySetRequest,
    *,
    progress: ProgressSink | None = None,
) -> SetCopyResult:
    """Execute one validated copy request through the core use case."""
    return CopySetUseCase().execute(request, progress=progress)


__all__ = ["execute"]
