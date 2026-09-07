"""Catalog scan use case and typed result contracts."""

from dataclasses import dataclass

from dj_digger.core.application.errors import InvalidInputError
from dj_digger.core.catalog.database import Database
from dj_digger.core.config import LibrarySourceConfig, WorkspaceConfig
from dj_digger.core.scanning.lifecycle import ScanLifecycle
from dj_digger.core.scanning.scanner import SourceScanner


@dataclass(frozen=True)
class ScanRequest:
    """Scope for one catalog scan."""

    source_id: str | None = None
    enabled_only: bool = False


@dataclass(frozen=True)
class ScanSourceResult:
    """Outcome for one configured source."""

    source_id: str
    succeeded: bool
    run_id: int | None
    error: str | None = None


@dataclass(frozen=True)
class ScanRunResult:
    """Immutable aggregate result for one scan request."""

    sources: tuple[ScanSourceResult, ...]


class ScanUseCase:
    """Reconcile configured source observations into the catalog."""

    def __init__(self, database: Database, config: WorkspaceConfig) -> None:
        self._database = database
        self._config = config

    def execute(self, request: ScanRequest) -> ScanRunResult:
        sources = self._selected_sources(request)
        lifecycle = ScanLifecycle(self._database)
        scanner = SourceScanner()
        results: list[ScanSourceResult] = []
        for source in sources:
            run_id: int | None = None
            try:
                run_id = lifecycle.begin(source.id)
                observation = scanner.scan(source, run_id)
                lifecycle.observe(run_id, observation)
                lifecycle.succeed(run_id)
            except Exception as error:
                if run_id is not None:
                    try:
                        lifecycle.fail(run_id, "scan", str(error))
                    except Exception:
                        pass
                results.append(ScanSourceResult(source.id, False, run_id, str(error)))
            else:
                results.append(ScanSourceResult(source.id, True, run_id))
        return ScanRunResult(tuple(results))

    def _selected_sources(self, request: ScanRequest) -> tuple[LibrarySourceConfig, ...]:
        sources = tuple(
            source for source in self._config.sources if not request.enabled_only or source.enabled
        )
        if request.source_id is None:
            return sources
        selected = tuple(source for source in sources if source.id == request.source_id)
        if not selected:
            raise InvalidInputError(f"unknown or disabled source: {request.source_id}")
        return selected
