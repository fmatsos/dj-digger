"""Command-line interface for DJ Digger."""

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from dj_digger.application import WorkspaceApplication
from dj_digger.config import WorkspaceConfig
from dj_digger.logging import RunLogger

app = typer.Typer(help="Catalog and export DJ music libraries.")


@app.callback()
def callback() -> None:
    """DJ Digger command-line application."""


ConfigOption = Annotated[Path, typer.Option("--config", exists=True, readable=True)]


def _run(config_path: Path, action: Any) -> None:
    config = WorkspaceConfig.load(config_path)
    logger = RunLogger(config.database)
    try:
        diagnostic = action(WorkspaceApplication(config))
    except Exception as error:
        diagnostic = {"event": "command", "status": "failed", "error": str(error)}
    logger.write(diagnostic)
    typer.echo(json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    if diagnostic.get("status") == "failed":
        raise typer.Exit(1)
    if diagnostic.get("status") == "partial":
        raise typer.Exit(2)


@app.command()
def scan(config: ConfigOption, source: Annotated[str | None, typer.Option()] = None) -> None:
    """Scan configured source roots and reconcile successful observations."""
    def action(service: WorkspaceApplication) -> dict[str, Any]:
        results = service.scan(source)
        return {
            "event": "scan",
            "status": "succeeded" if all(result.succeeded for result in results) else "failed",
            "scans": [result.__dict__ for result in results],
        }

    _run(config, action)


@app.command()
def metadata(
    config: ConfigOption,
    source: Annotated[str | None, typer.Option()] = None,
    path: Annotated[str | None, typer.Option()] = None,
    force: Annotated[bool, typer.Option()] = False,
) -> None:
    """Refresh embedded metadata for current tracks."""
    def action(service: WorkspaceApplication) -> dict[str, Any]:
        result = service.metadata(source, path_prefix=path, force=force)
        return {"event": "metadata", "status": _result_status(result), **result.__dict__}

    _run(config, action)


@app.command()
def analyze(
    config: ConfigOption,
    source: Annotated[str | None, typer.Option()] = None,
    path: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int | None, typer.Option()] = None,
    force: Annotated[bool, typer.Option()] = False,
    workers: Annotated[int, typer.Option()] = 1,
) -> None:
    """Analyze selected tracks with bounded worker concurrency."""
    def action(service: WorkspaceApplication) -> dict[str, Any]:
        result = service.analyze(
            source, path_prefix=path, limit=limit, force=force, workers=workers
        )
        return {"event": "analyze", "status": _result_status(result), **result.__dict__}

    _run(config, action)


@app.command()
def export(config: ConfigOption, facet: Annotated[str | None, typer.Option()] = None) -> None:
    """Publish canonical catalog facets."""
    _run(
        config,
        lambda service: {
            "event": "export",
            "status": "succeeded",
            "exports": service.export(facet),
        },
    )


@app.command()
def snapshot(
    config: ConfigOption,
    output: Annotated[Path, typer.Option()],
    archive: Annotated[bool, typer.Option()] = False,
) -> None:
    """Create a validated, optionally archived export snapshot."""
    _run(
        config,
        lambda service: {
            "event": "snapshot",
            "status": "succeeded",
            "directory": str((result := service.snapshot(output, archive)).directory),
            "archive": None if result.archive is None else str(result.archive),
        },
    )


@app.command()
def doctor(config: ConfigOption) -> None:
    """Check workspace roots, schema migrations, and required binaries."""
    _run(config, lambda service: service.doctor())


@app.command()
def status(config: ConfigOption) -> None:
    """Report source freshness and currently known catalog state."""
    _run(config, lambda service: service.status())


@app.command()
def refresh(config: ConfigOption) -> None:
    """Scan enabled sources, refresh metadata, then publish canonical exports."""
    _run(config, lambda service: service.refresh())


def main() -> None:
    """Run the DJ Digger command-line application."""
    app()


def _result_status(result: Any) -> str:
    status = getattr(result, "status", None)
    if isinstance(status, str) and status in {"succeeded", "partial", "failed"}:
        return status
    failed = int(getattr(result, "failed", 0))
    analyzed = int(getattr(result, "analyzed", 0))
    return "failed" if failed and not analyzed else ("partial" if failed else "succeeded")


if __name__ == "__main__":
    main()
