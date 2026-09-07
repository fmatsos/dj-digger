"""Command-line interface for DJ Digger."""

import json
import math
import os
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from dj_digger.cli import background
from dj_digger.cli.commands.analyze import execute as execute_analyze
from dj_digger.cli.commands.copy import execute as execute_copy
from dj_digger.cli.commands.curation import curation_app
from dj_digger.cli.commands.duplicates import execute as execute_duplicates
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
from dj_digger.cli.rich_progress import RichProgressReporter
from dj_digger.cli.runtime import ConfigLoadError, config_failure, load_config
from dj_digger.cli.terminal import render
from dj_digger.core.application import (
    AnalyzeRequest,
    CopySetRequest,
    CoreApplication,
    DuplicateAnalyzeRequest,
    DuplicateListRequest,
    DuplicateMarkBestRequest,
    ExportRequest,
    RefreshRequest,
    SnapshotRequest,
)
from dj_digger.core.run_log import RunLogger

install_patches()

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


def _run(
    config_path: Path, action: Any, *, event: str = "command", json_output: bool = False
) -> None:
    package = sys.modules.get("dj_digger.cli")
    application_type = (
        CoreApplication if package is None else getattr(package, "CoreApplication", CoreApplication)
    )
    logger_type = RunLogger if package is None else getattr(package, "RunLogger", RunLogger)
    try:
        config = load_config(config_path)
    except ConfigLoadError as error:
        diagnostic = config_failure(event, error)
        if json_output:
            typer.echo(
                json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
        else:
            render(diagnostic)
        raise typer.Exit(1) from None
    logger = logger_type(config.database)
    try:
        with application_type(config) as service:
            diagnostic = action(service)
    except Exception as error:
        diagnostic = {"event": event, "status": "failed", "error": str(error)}
    logger.write(diagnostic)
    job_id = background.current_job_id()
    if job_id is not None:
        background.record_result(config.database, job_id, diagnostic)
    if json_output:
        typer.echo(
            json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    else:
        render(diagnostic)
    if diagnostic.get("status") == "failed":
        raise typer.Exit(1)
    if diagnostic.get("status") == "partial":
        raise typer.Exit(2)


def _run_in_background(
    config_path: Path, command: str, argv: list[str], *, json_output: bool = False
) -> None:
    try:
        config = load_config(config_path)
    except ConfigLoadError as error:
        diagnostic = config_failure(command, error)
        if json_output:
            typer.echo(
                json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
        else:
            render(diagnostic)
        raise typer.Exit(1) from None
    info = background.launch(config.database, command, argv)
    diagnostic = {"event": command, "status": "background", **info}
    if json_output:
        typer.echo(
            json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    else:
        render(diagnostic)


def _progress_reporter() -> type[RichProgressReporter]:
    package = sys.modules.get("dj_digger.cli")
    if package is None:
        return RichProgressReporter
    return getattr(package, "RichProgressReporter", RichProgressReporter)


@app.command()
def scan(
    config: ConfigOption,
    source: Annotated[str | None, typer.Option()] = None,
    json_output: JsonOption = False,
) -> None:
    """Scan configured source roots and reconcile successful observations."""
    diagnostic = execute_scan(config, source)
    if json_output:
        typer.echo(
            json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    else:
        render(diagnostic)
    if diagnostic.get("status") == "failed":
        raise typer.Exit(1)


@app.command()
def metadata(
    config: ConfigOption,
    source: Annotated[str | None, typer.Option()] = None,
    path: Annotated[str | None, typer.Option()] = None,
    force: Annotated[bool, typer.Option()] = False,
    json_output: JsonOption = False,
) -> None:
    """Refresh embedded metadata for current tracks."""
    diagnostic = execute_metadata(config, source, path, force)
    if json_output:
        typer.echo(
            json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    else:
        render(diagnostic)
    if diagnostic.get("status") == "failed":
        raise typer.Exit(1)
    if diagnostic.get("status") == "partial":
        raise typer.Exit(2)


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

    def action(service: CoreApplication) -> dict[str, Any]:
        with _progress_reporter()(verbosity=ctx.obj.get("verbosity", 0)) as progress:
            return execute_analyze(
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
            )

    _run(config, action, event="analyze", json_output=json_output)


@app.command()
def duplicates(
    config: ConfigOption,
    ctx: typer.Context,
    analyze: Annotated[bool, typer.Option("--analyze")] = False,
    list_: Annotated[bool, typer.Option("--list")] = False,
    mark_best_quality: Annotated[bool, typer.Option("--mark-best-quality")] = False,
    mastering: Annotated[bool, typer.Option("--mastering")] = False,
    dj_review: Annotated[bool, typer.Option("--dj-review")] = False,
    source: Annotated[str | None, typer.Option()] = None,
    workers: PositiveWorkersOption = 1,
    track_timeout: TrackTimeoutOption = 1800.0,
    background: BackgroundOption = False,
    json_output: JsonOption = False,
) -> None:
    """Fingerprint audio, list duplicate recordings, and mark the best-quality copy."""
    if not (analyze or list_ or mark_best_quality):
        raise typer.BadParameter("one of --analyze, --list, or --mark-best-quality is required")
    if analyze and list_:
        raise typer.BadParameter("--analyze and --list are mutually exclusive")
    if list_ and mark_best_quality:
        raise typer.BadParameter("--list and --mark-best-quality are mutually exclusive")
    if mastering and not analyze:
        raise typer.BadParameter("--mastering is only valid with --analyze")
    if dj_review and not list_:
        raise typer.BadParameter("--dj-review is only valid with --list")
    if not analyze:
        if _was_passed_on_command_line(ctx, "workers"):
            raise typer.BadParameter("--workers is only valid with --analyze")
        if _was_passed_on_command_line(ctx, "track_timeout"):
            raise typer.BadParameter("--track-timeout is only valid with --analyze")
        if background:
            raise typer.BadParameter("--background is only valid with --analyze")

    if background:
        argv = ["duplicates", "--config", str(config), "--analyze"]
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

    def action(service: CoreApplication) -> dict[str, Any]:
        if list_:
            return execute_duplicates(
                service,
                DuplicateListRequest(source_id=source),
                dj_review=dj_review,
            )
        if analyze:
            with _progress_reporter()(verbosity=ctx.obj.get("verbosity", 0)) as progress:
                return execute_duplicates(
                    service,
                    DuplicateAnalyzeRequest(
                        source_id=source,
                        workers=workers,
                        track_timeout=track_timeout,
                        mark_best_quality=mark_best_quality,
                        mastering=mastering,
                    ),
                    progress=progress,
                )
        return execute_duplicates(
            service,
            DuplicateMarkBestRequest(source_id=source),
        )

    _run(config, action, event="duplicates", json_output=json_output)


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
    _run(
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
        raise typer.Exit(1) from None
    if json_output:
        typer.echo(json.dumps(copy_payload(result), separators=(",", ":")))
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
    _run(
        config,
        lambda service: execute_snapshot(service, SnapshotRequest(output, archive)),
        event="snapshot",
        json_output=json_output,
    )


@app.command()
def doctor(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Check workspace roots, schema migrations, and required binaries."""
    _run(config, execute_doctor, event="doctor", json_output=json_output)


@app.command()
def status(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Report source freshness and currently known catalog state."""
    _run(config, execute_status, event="status", json_output=json_output)


@database_app.command("optimize")
def database_optimize(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Update SQLite planner statistics when useful."""
    _run(config, execute_optimize, event="database.optimize", json_output=json_output)


@database_app.command("quick-check")
def database_quick_check(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Run SQLite's lightweight consistency check."""
    _run(config, execute_quick_check, event="database.quick-check", json_output=json_output)


@database_app.command("integrity-check")
def database_integrity_check(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Run SQLite's explicit full integrity check."""
    _run(config, execute_integrity_check, event="database.integrity-check", json_output=json_output)


@database_app.command("rebuild-current-analysis")
def database_rebuild_current_analysis(
    config: ConfigOption, json_output: JsonOption = False
) -> None:
    """Rebuild the derived latest-successful-analysis projection."""
    _run(
        config,
        execute_rebuild,
        event="database.rebuild-current-analysis",
        json_output=json_output,
    )


@app.command()
def refresh(
    config: ConfigOption,
    ctx: typer.Context,
    workers: PositiveWorkersOption = 1,
    track_timeout: TrackTimeoutOption = 1800.0,
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

    def action(service: CoreApplication) -> dict[str, Any]:
        with _progress_reporter()(verbosity=ctx.obj.get("verbosity", 0)) as progress:
            return execute_refresh(
                service,
                RefreshRequest(workers=workers, track_timeout=track_timeout),
                progress=progress,
            )

    _run(config, action, event="refresh", json_output=json_output)


@app.command()
def jobs(config: ConfigOption, json_output: JsonOption = False) -> None:
    """List background jobs launched with --background and their status."""
    try:
        workspace_config = load_config(config)
    except ConfigLoadError as error:
        diagnostic = config_failure("jobs", error)
        if json_output:
            typer.echo(
                json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
        else:
            render(diagnostic)
        raise typer.Exit(1) from None
    payload = jobs_payload(background.list_jobs(workspace_config.database))
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        render(payload)


def main() -> None:
    """Run the DJ Digger command-line application."""
    app()


if __name__ == "__main__":
    main()
