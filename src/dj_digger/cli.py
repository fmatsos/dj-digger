"""Command-line interface for DJ Digger."""

import json
import math
from pathlib import Path
from typing import Annotated, Any

import typer

from dj_digger.application import WorkspaceApplication
from dj_digger.config import WorkspaceConfig
from dj_digger.logging import RunLogger
from dj_digger.rich_progress import RichProgressReporter
from dj_digger.set_copy import copy_set

app = typer.Typer(
    help="Catalog and export DJ music libraries.",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@app.callback()
def callback(
    ctx: typer.Context,
    verbose: Annotated[int, typer.Option("-v", "--verbose", count=True)] = 0,
) -> None:
    """DJ Digger command-line application."""
    ctx.ensure_object(dict)
    ctx.obj["verbosity"] = verbose
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


ConfigOption = Annotated[Path, typer.Option("--config", exists=True, readable=True)]


def _positive_track_timeout(value: float) -> float:
    if not math.isfinite(value) or value <= 0:
        raise typer.BadParameter("must be greater than zero")
    return value


def _positive_workers(value: int) -> int:
    if value <= 0:
        raise typer.BadParameter("must be greater than zero")
    return value


TrackTimeoutOption = Annotated[
    float,
    typer.Option(
        "--track-timeout",
        callback=_positive_track_timeout,
        help="Maximum seconds allowed for one track analysis.",
    ),
]
PositiveWorkersOption = Annotated[
    int,
    typer.Option("--workers", callback=_positive_workers),
]


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
    ctx: typer.Context,
    source: Annotated[str | None, typer.Option()] = None,
    path: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int | None, typer.Option()] = None,
    force: Annotated[bool, typer.Option()] = False,
    workers: PositiveWorkersOption = 1,
    track_timeout: TrackTimeoutOption = 1800.0,
) -> None:
    """Analyze selected tracks with bounded worker concurrency."""
    def action(service: WorkspaceApplication) -> dict[str, Any]:
        with RichProgressReporter(verbosity=ctx.obj.get("verbosity", 0)) as progress:
            result = service.analyze(
                source,
                path_prefix=path,
                limit=limit,
                force=force,
                workers=workers,
                track_timeout=track_timeout,
                progress=progress,
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
def copy(
    library: Annotated[Path, typer.Option("-l", "--library")],
    output: Annotated[Path, typer.Option("-o", "--output")],
    playlist: Annotated[list[Path] | None, typer.Option("-p", "--playlist")] = None,
    track: Annotated[list[str] | None, typer.Option("-t", "--track")] = None,
    owner: Annotated[str, typer.Option("--owner", help="Output owner in USER:GROUP format.")] = (
        "share:share"
    ),
    verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False,
) -> None:
    """Copy an ordered set from a read-only music library."""
    tracks = track or []
    playlists = playlist or []
    if len(playlists) > 1:
        raise typer.BadParameter("Only one --playlist may be provided")
    playlist_path = playlists[0] if playlists else None
    if playlist_path is None and not tracks:
        raise typer.BadParameter("At least one --playlist or --track is required")

    def started(total: int) -> None:
        typer.echo(f"[  0%] (0/{total})")

    def report(
        event: str, index: int, total: int, group: str, source: str, target: str
    ) -> None:
        if event == "before" and verbose:
            width = max(2, len(str(total)))
            typer.echo(
                f"COPY {index:0{width}d}/{total}\n"
                f"  group: {group or '(root)'}\n  from:  {source}\n  to:    {target}"
            )
        if event == "after":
            typer.echo(f"[{index * 100 // total:3d}%] ({index}/{total})")

    try:
        result = copy_set(
            library=library,
            output=output,
            playlist=playlist_path,
            tracks=tracks,
            owner=owner,
            started=started,
            progress=report,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from None
    if verbose:
        typer.echo(f"\nOWNERSHIP {owner} -> {output.resolve()}")
        typer.echo(f"\nPlaylist: {result.playlist}\nText list: {result.text_list}")


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
def refresh(
    config: ConfigOption,
    ctx: typer.Context,
    workers: PositiveWorkersOption = 1,
    track_timeout: TrackTimeoutOption = 1800.0,
) -> None:
    """Scan enabled sources, refresh metadata, then publish canonical exports."""
    def action(service: WorkspaceApplication) -> dict[str, Any]:
        with RichProgressReporter(verbosity=ctx.obj.get("verbosity", 0)) as progress:
            return service.refresh(
                progress=progress,
                workers=workers,
                track_timeout=track_timeout,
            )

    _run(config, action)


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
