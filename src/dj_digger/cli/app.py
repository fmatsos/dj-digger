"""Command-line interface for DJ Digger."""

import logging
import math
import os
from pathlib import Path
from typing import Annotated, Any

import typer

import dj_digger.cli.background as background
from dj_digger.cli.commands.analyze import execute as execute_analyze
from dj_digger.cli.commands.copy import execute as execute_copy
from dj_digger.cli.commands.curation import curation_app
from dj_digger.cli.commands.duplicates import (
    execute_analyze as execute_duplicates_analyze,
)
from dj_digger.cli.commands.duplicates import (
    execute_list as execute_duplicates_list,
)
from dj_digger.cli.commands.duplicates import (
    execute_mark_best as execute_duplicates_mark_best,
)
from dj_digger.cli.commands.export import execute as execute_export
from dj_digger.cli.commands.mcp import serve as serve_mcp
from dj_digger.cli.commands.metadata import execute as execute_metadata
from dj_digger.cli.commands.operations import (
    execute_doctor,
    execute_integrity_check,
    execute_optimize,
    execute_quick_check,
    execute_rebuild,
    execute_status,
)
from dj_digger.cli.commands.refresh import execute as execute_refresh
from dj_digger.cli.commands.scan import execute as execute_scan
from dj_digger.cli.commands.snapshot import execute as execute_snapshot
from dj_digger.cli.completion import install_patches
from dj_digger.cli.presenters.copy import copy_payload, copy_progress_lines
from dj_digger.cli.presenters.jobs import jobs_payload
from dj_digger.cli.runtime import (
    EXIT_FAILED,
    configure_logging,
    emit_json,
    run_command,
    run_command_with_progress,
    run_with_config,
)
from dj_digger.core.analysis.config import DEFAULT_TRACK_TIMEOUT_SECONDS, DEFAULT_WORKERS
from dj_digger.core.application import (
    AnalyzeRequest,
    CopySetRequest,
    DuplicateAnalyzeRequest,
    DuplicateListRequest,
    DuplicateMarkBestRequest,
    ExportRequest,
    MetadataRequest,
    RefreshRequest,
    ScanRequest,
    SnapshotRequest,
)
from dj_digger.core.diagnostics import DiagnosticStatus

_logger = logging.getLogger("dj_digger")

app = typer.Typer(
    help="Catalog and export DJ music libraries.",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
database_app = typer.Typer(help="Inspect and maintain the SQLite catalog.")
app.add_typer(database_app, name="database")
app.add_typer(curation_app, name="curation")


@app.callback()
def callback(
    ctx: typer.Context,
    verbose: Annotated[int, typer.Option("-v", "--verbose", count=True)] = 0,
) -> None:
    """DJ Digger command-line application."""
    ctx.ensure_object(dict)
    ctx.obj["verbosity"] = verbose
    configure_logging(verbose)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def _default_config_path() -> Path:
    workspace = Path.cwd()
    candidates = (
        workspace / "config.toml",
        workspace / "config" / "config.toml",
        Path.home() / ".dj-digger" / "config.toml",
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.R_OK):
            return candidate.resolve()
    raise typer.BadParameter(
        "no configuration file found; pass --config PATH or create "
        "config.toml, config/config.toml, or ~/.dj-digger/config.toml"
    )


ConfigOption = Annotated[
    Path,
    typer.Option(
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        default_factory=_default_config_path,
        show_default=False,
        help="Workspace config; discovered automatically when omitted.",
    ),
]


JsonOption = Annotated[
    bool, typer.Option("--json", help="Emit the compact machine-readable JSON payload.")
]


@app.command("mcp")
def mcp_server(config: ConfigOption) -> None:
    """Serve bounded curation reads and draft creation over MCP stdio."""
    serve_mcp(config)


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
BackgroundOption = Annotated[
    bool,
    typer.Option("--background", help="Detach and run this command in the background."),
]


def _run_in_background(
    config_path: Path, command: str, argv: list[str], *, json_output: bool = False
) -> None:
    run_with_config(
        config_path,
        lambda config: {
            "event": command,
            "status": DiagnosticStatus.BACKGROUND,
            **background.launch(config.database, command, argv),
        },
        event=command,
        json_output=json_output,
    )


@app.command()
def scan(
    config: ConfigOption,
    source: Annotated[str | None, typer.Option()] = None,
    json_output: JsonOption = False,
) -> None:
    """Scan configured source roots and reconcile successful observations."""
    run_command(
        config,
        lambda service: execute_scan(service, ScanRequest(source_id=source)),
        event="scan",
        json_output=json_output,
    )


@app.command()
def metadata(
    config: ConfigOption,
    source: Annotated[str | None, typer.Option()] = None,
    path: Annotated[str | None, typer.Option()] = None,
    force: Annotated[bool, typer.Option()] = False,
    json_output: JsonOption = False,
) -> None:
    """Refresh embedded metadata for current tracks."""
    run_command(
        config,
        lambda service: execute_metadata(
            service, MetadataRequest(source_id=source, path_prefix=path, force=force)
        ),
        event="metadata",
        json_output=json_output,
    )


@app.command()
def analyze(
    config: ConfigOption,
    ctx: typer.Context,
    source: Annotated[str | None, typer.Option()] = None,
    path: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int | None, typer.Option()] = None,
    force: Annotated[bool, typer.Option()] = False,
    workers: PositiveWorkersOption = DEFAULT_WORKERS,
    track_timeout: TrackTimeoutOption = DEFAULT_TRACK_TIMEOUT_SECONDS,
    background: BackgroundOption = False,
    json_output: JsonOption = False,
) -> None:
    """Analyze selected tracks with bounded worker concurrency."""
    if background:
        argv = ["analyze", "--config", str(config)]
        if source is not None:
            argv += ["--source", source]
        if path is not None:
            argv += ["--path", path]
        if limit is not None:
            argv += ["--limit", str(limit)]
        if force:
            argv.append("--force")
        argv += ["--workers", str(workers), "--track-timeout", str(track_timeout)]
        if json_output:
            argv.append("--json")
        _run_in_background(config, "analyze", argv, json_output=json_output)
        return

    run_command_with_progress(
        config,
        lambda service, progress: execute_analyze(
            service,
            AnalyzeRequest(
                source_id=source,
                path_prefix=path,
                limit=limit,
                force=force,
                workers=workers,
                track_timeout=track_timeout,
            ),
            progress=progress,
        ),
        event="analyze",
        verbosity=ctx.obj.get("verbosity", 0),
        json_output=json_output,
    )


duplicates_app = typer.Typer(
    help="Fingerprint audio, list duplicate recordings, and mark the best-quality copy.",
    invoke_without_command=True,
)
app.add_typer(duplicates_app, name="duplicates")

#: The callback cannot use ``ConfigOption``: its default factory would run (and
#: fail) even when a subcommand carries its own ``--config``.
LegacyConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        show_default=False,
        help="Workspace config; discovered automatically when omitted.",
    ),
]
SourceOption = Annotated[str | None, typer.Option("--source")]


def _duplicates_analyze(
    ctx: typer.Context,
    config: Path,
    *,
    source: str | None,
    mastering: bool,
    mark_best_quality: bool,
    workers: int,
    track_timeout: float,
    background: bool,
    json_output: bool,
) -> None:
    """Run one duplicate analysis, in the foreground or detached."""
    if background:
        argv = ["duplicates", "analyze", "--config", str(config)]
        if source is not None:
            argv += ["--source", source]
        argv += ["--workers", str(workers), "--track-timeout", str(track_timeout)]
        if mark_best_quality:
            argv.append("--mark-best-quality")
        if mastering:
            argv.append("--mastering")
        if json_output:
            argv.append("--json")
        _run_in_background(config, "duplicates", argv, json_output=json_output)
        return
    run_command_with_progress(
        config,
        lambda service, progress: execute_duplicates_analyze(
            service,
            DuplicateAnalyzeRequest(
                source_id=source,
                workers=workers,
                track_timeout=track_timeout,
                mark_best_quality=mark_best_quality,
                mastering=mastering,
            ),
            progress=progress,
        ),
        event="duplicates",
        verbosity=ctx.obj.get("verbosity", 0),
        json_output=json_output,
    )


@duplicates_app.command("analyze")
def duplicates_analyze(
    ctx: typer.Context,
    config: ConfigOption,
    source: SourceOption = None,
    mastering: Annotated[bool, typer.Option("--mastering")] = False,
    mark_best_quality: Annotated[bool, typer.Option("--mark-best-quality")] = False,
    workers: PositiveWorkersOption = DEFAULT_WORKERS,
    track_timeout: TrackTimeoutOption = DEFAULT_TRACK_TIMEOUT_SECONDS,
    background: BackgroundOption = False,
    json_output: JsonOption = False,
) -> None:
    """Fingerprint present tracks and derive duplicate groups."""
    _duplicates_analyze(
        ctx,
        config,
        source=source,
        mastering=mastering,
        mark_best_quality=mark_best_quality,
        workers=workers,
        track_timeout=track_timeout,
        background=background,
        json_output=json_output,
    )


@duplicates_app.command("list")
def duplicates_list(
    config: ConfigOption,
    source: SourceOption = None,
    dj_review: Annotated[bool, typer.Option("--dj-review")] = False,
    json_output: JsonOption = False,
) -> None:
    """List known duplicate groups without touching the catalog."""
    run_command(
        config,
        lambda service: execute_duplicates_list(
            service, DuplicateListRequest(source_id=source), dj_review=dj_review
        ),
        event="duplicates",
        json_output=json_output,
    )


@duplicates_app.command("mark-best-quality")
def duplicates_mark_best_quality(
    config: ConfigOption,
    source: SourceOption = None,
    json_output: JsonOption = False,
) -> None:
    """Mark the best-quality copy in each duplicate group."""
    run_command(
        config,
        lambda service: execute_duplicates_mark_best(
            service, DuplicateMarkBestRequest(source_id=source)
        ),
        event="duplicates",
        json_output=json_output,
    )


@duplicates_app.callback()
def duplicates(
    ctx: typer.Context,
    config: LegacyConfigOption = None,
    analyze: Annotated[bool, typer.Option("--analyze", hidden=True)] = False,
    list_: Annotated[bool, typer.Option("--list", hidden=True)] = False,
    mark_best_quality: Annotated[bool, typer.Option("--mark-best-quality", hidden=True)] = False,
    mastering: Annotated[bool, typer.Option("--mastering", hidden=True)] = False,
    dj_review: Annotated[bool, typer.Option("--dj-review", hidden=True)] = False,
    source: Annotated[str | None, typer.Option("--source", hidden=True)] = None,
    workers: Annotated[int, typer.Option("--workers", hidden=True)] = DEFAULT_WORKERS,
    track_timeout: Annotated[
        float, typer.Option("--track-timeout", hidden=True)
    ] = DEFAULT_TRACK_TIMEOUT_SECONDS,
    background: Annotated[bool, typer.Option("--background", hidden=True)] = False,
    json_output: Annotated[bool, typer.Option("--json", hidden=True)] = False,
) -> None:
    """Accept the retired flag form so existing scripts keep working."""
    if ctx.invoked_subcommand is not None:
        return
    selected = [
        name
        for name, chosen in (
            ("analyze", analyze),
            ("list", list_),
            ("mark-best-quality", mark_best_quality),
        )
        if chosen
    ]
    if not selected:
        raise typer.BadParameter("one of --analyze, --list, or --mark-best-quality is required")
    if len(selected) > 1 and selected != ["analyze", "mark-best-quality"]:
        raise typer.BadParameter(f"--{selected[0]} and --{selected[1]} are mutually exclusive")
    workflow = selected[0]
    # The retired form keeps its own exclusivity checks so a stale script is told
    # about an ignored option instead of silently getting different behaviour.
    if workflow != "analyze":
        for option, name in (("--workers", "workers"), ("--track-timeout", "track_timeout")):
            if _was_passed_on_command_line(ctx, name):
                raise typer.BadParameter(f"{option} is only valid with --analyze")
        if background:
            raise typer.BadParameter("--background is only valid with --analyze")
        if mastering:
            raise typer.BadParameter("--mastering is only valid with --analyze")
    if dj_review and workflow != "list":
        raise typer.BadParameter("--dj-review is only valid with --list")
    _logger.warning(
        "`dj-digger duplicates --%s` is deprecated; use `dj-digger duplicates %s` instead",
        workflow,
        workflow,
    )
    resolved = config if config is not None else _default_config_path()
    if workflow == "analyze":
        _duplicates_analyze(
            ctx,
            resolved,
            source=source,
            mastering=mastering,
            mark_best_quality=mark_best_quality,
            workers=_positive_workers(workers),
            track_timeout=_positive_track_timeout(track_timeout),
            background=background,
            json_output=json_output,
        )
        return
    if workflow == "list":
        duplicates_list(resolved, source=source, dj_review=dj_review, json_output=json_output)
        return
    duplicates_mark_best_quality(resolved, source=source, json_output=json_output)


def _was_passed_on_command_line(ctx: typer.Context, name: str) -> bool:
    source = ctx.get_parameter_source(name)
    return source is not None and source.name == "COMMANDLINE"


@app.command()
def export(
    config: ConfigOption,
    facet: Annotated[str | None, typer.Option("--facet")] = None,
    type_: Annotated[str | None, typer.Option("--type")] = None,
    format_: Annotated[str | None, typer.Option("--format")] = None,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: JsonOption = False,
) -> None:
    """Publish canonical catalog facets."""
    run_command(
        config,
        lambda service: execute_export(
            service,
            ExportRequest(facet=facet, type=type_, format=format_, fields=fields),
        ),
        event="export",
        json_output=json_output,
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
    json_output: JsonOption = False,
) -> None:
    """Copy an ordered set from a read-only music library."""
    tracks = track or []
    playlists = playlist or []
    if len(playlists) > 1:
        raise typer.BadParameter("Only one --playlist may be provided")
    playlist_path = playlists[0] if playlists else None
    if playlist_path is None and not tracks:
        raise typer.BadParameter("At least one --playlist or --track is required")

    def report(event: Any) -> None:
        for line in copy_progress_lines(event, verbose=verbose):
            typer.echo(line)

    try:
        result = execute_copy(
            CopySetRequest(
                library=library,
                output=output,
                playlist=playlist_path,
                tracks=tuple(tracks),
                owner=owner,
            ),
            progress=None if json_output else report,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(EXIT_FAILED) from None
    if json_output:
        emit_json(copy_payload(result))
    elif verbose:
        typer.echo(f"\nOWNERSHIP {owner} -> {output.resolve()}")
        typer.echo(f"\nPlaylist: {result.playlist}\nText list: {result.text_list}")


@app.command()
def snapshot(
    config: ConfigOption,
    output: Annotated[Path, typer.Option()],
    archive: Annotated[bool, typer.Option()] = False,
    json_output: JsonOption = False,
) -> None:
    """Create a validated, optionally archived export snapshot."""
    run_command(
        config,
        lambda service: execute_snapshot(service, SnapshotRequest(output, archive)),
        event="snapshot",
        json_output=json_output,
    )


@app.command()
def doctor(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Check workspace roots, schema migrations, and required binaries."""
    run_command(config, execute_doctor, event="doctor", json_output=json_output)


@app.command()
def status(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Report source freshness and currently known catalog state."""
    run_command(config, execute_status, event="status", json_output=json_output)


@database_app.command("optimize")
def database_optimize(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Update SQLite planner statistics when useful."""
    run_command(config, execute_optimize, event="database.optimize", json_output=json_output)


@database_app.command("quick-check")
def database_quick_check(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Run SQLite's lightweight consistency check."""
    run_command(config, execute_quick_check, event="database.quick-check", json_output=json_output)


@database_app.command("integrity-check")
def database_integrity_check(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Run SQLite's explicit full integrity check."""
    run_command(
        config,
        execute_integrity_check,
        event="database.integrity-check",
        json_output=json_output,
    )


@database_app.command("rebuild-current-analysis")
def database_rebuild_current_analysis(
    config: ConfigOption, json_output: JsonOption = False
) -> None:
    """Rebuild the derived latest-successful-analysis projection."""
    run_command(
        config,
        execute_rebuild,
        event="database.rebuild-current-analysis",
        json_output=json_output,
    )


@app.command()
def refresh(
    config: ConfigOption,
    ctx: typer.Context,
    workers: PositiveWorkersOption = DEFAULT_WORKERS,
    track_timeout: TrackTimeoutOption = DEFAULT_TRACK_TIMEOUT_SECONDS,
    background: BackgroundOption = False,
    json_output: JsonOption = False,
) -> None:
    """Scan enabled sources, refresh metadata, then publish canonical exports."""
    if background:
        argv = ["refresh", "--config", str(config), "--workers", str(workers)]
        argv += ["--track-timeout", str(track_timeout)]
        if json_output:
            argv.append("--json")
        _run_in_background(config, "refresh", argv, json_output=json_output)
        return

    run_command_with_progress(
        config,
        lambda service, progress: execute_refresh(
            service,
            RefreshRequest(workers=workers, track_timeout=track_timeout),
            progress=progress,
        ),
        event="refresh",
        verbosity=ctx.obj.get("verbosity", 0),
        json_output=json_output,
    )


@app.command()
def jobs(config: ConfigOption, json_output: JsonOption = False) -> None:
    """List background jobs launched with --background and their status."""
    run_with_config(
        config,
        lambda workspace: jobs_payload(background.list_jobs(workspace.database)),
        event="jobs",
        json_output=json_output,
    )


def main() -> None:
    """Run the DJ Digger command-line application."""
    install_patches()
    app()


if __name__ == "__main__":
    main()
