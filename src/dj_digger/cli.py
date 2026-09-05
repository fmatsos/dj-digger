"""Command-line interface for DJ Digger."""

import json
import math
import os
from pathlib import Path
from typing import Annotated, Any

import typer

from dj_digger import background
from dj_digger.application import WorkspaceApplication
from dj_digger.completion import install_patches
from dj_digger.config import WorkspaceConfig
from dj_digger.logging import RunLogger
from dj_digger.rich_progress import RichProgressReporter
from dj_digger.set_copy import copy_set
from dj_digger.terminal import render

install_patches()

app = typer.Typer(
    help="Catalog and export DJ music libraries.",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
database_app = typer.Typer(help="Inspect and maintain the SQLite catalog.")
app.add_typer(database_app, name="database")


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
JsonOption = Annotated[
    bool, typer.Option("--json", help="Emit the compact machine-readable JSON payload.")
]


def _run(config_path: Path, action: Any, *, json_output: bool = False) -> None:
    config = WorkspaceConfig.load(config_path)
    logger = RunLogger(config.database)
    try:
        with WorkspaceApplication(config) as service:
            diagnostic = action(service)
    except Exception as error:
        diagnostic = {"event": "command", "status": "failed", "error": str(error)}
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
    config = WorkspaceConfig.load(config_path)
    info = background.launch(config.database, command, argv)
    diagnostic = {"event": command, "status": "background", **info}
    if json_output:
        typer.echo(
            json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    else:
        render(diagnostic)


@app.command()
def scan(
    config: ConfigOption,
    source: Annotated[str | None, typer.Option()] = None,
    json_output: JsonOption = False,
) -> None:
    """Scan configured source roots and reconcile successful observations."""

    def action(service: WorkspaceApplication) -> dict[str, Any]:
        results = service.scan(source)
        return {
            "event": "scan",
            "status": "succeeded" if all(result.succeeded for result in results) else "failed",
            "scans": [result.__dict__ for result in results],
        }

    _run(config, action, json_output=json_output)


@app.command()
def metadata(
    config: ConfigOption,
    source: Annotated[str | None, typer.Option()] = None,
    path: Annotated[str | None, typer.Option()] = None,
    force: Annotated[bool, typer.Option()] = False,
    json_output: JsonOption = False,
) -> None:
    """Refresh embedded metadata for current tracks."""

    def action(service: WorkspaceApplication) -> dict[str, Any]:
        result = service.metadata(source, path_prefix=path, force=force)
        return {"event": "metadata", "status": _result_status(result), **result.__dict__}

    _run(config, action, json_output=json_output)


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

    _run(config, action, json_output=json_output)


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

    def action(service: WorkspaceApplication) -> dict[str, Any]:
        if list_:
            groups = service.duplicates_list(source)
            if dj_review:
                groups = [
                    group
                    for group in groups
                    if getattr(group, "dj_review_recommended", None) is True
                ]
                groups.sort(key=lambda group: _review_sort_key(group))
            return {
                "event": "duplicates",
                "status": "succeeded",
                "groups": [_group_json(group) for group in groups],
            }
        if analyze:
            with RichProgressReporter(verbosity=ctx.obj.get("verbosity", 0)) as progress:
                result = service.duplicates_analyze(
                    source,
                    workers=workers,
                    track_timeout=track_timeout,
                    mark_best_quality=mark_best_quality,
                    mastering=mastering,
                    progress=progress,
                )
            return {
                "event": "duplicates",
                "status": _result_status(result),
                **result.__dict__,
            }
        mark_result = service.duplicates_mark_best_quality(source)
        return {
            "event": "duplicates",
            "status": mark_result.status,
            "marked_best": mark_result.marked_best,
            "incomplete_track_ids": list(mark_result.incomplete_track_ids),
        }

    _run(config, action, json_output=json_output)


def _was_passed_on_command_line(ctx: typer.Context, name: str) -> bool:
    source = ctx.get_parameter_source(name)
    return source is not None and source.name == "COMMANDLINE"


def _group_json(group: Any) -> dict[str, Any]:
    return {
        "group_id": group.group_id,
        "mastering_variant": getattr(group, "mastering_variant", None),
        "dj_review_recommended": getattr(group, "dj_review_recommended", None),
        "analysis_complete": getattr(group, "analysis_complete", False),
        "comparison_status": getattr(group, "comparison_status", "missing_best_quality"),
        "members": [
            {
                "source": member.source_id,
                "track_id": member.track_id,
                "relative_path": member.relative_path,
                "technical_facts": member.technical_facts,
                "best_quality": member.best_quality,
                "audio_analysis": getattr(member, "audio_analysis", None),
                "dj_analysis": getattr(member, "dj_analysis", None),
                "mastering_comparison": (
                    None
                    if getattr(member, "mastering_comparison", None) is None
                    else member.mastering_comparison.__dict__
                ),
            }
            for member in group.members
        ],
    }


def _review_sort_key(group: Any) -> tuple[int, float, float, str]:
    deficits = [
        member.dj_analysis.get("gain_deficit_db")
        for member in group.members
        if member.dj_analysis is not None and member.dj_analysis.get("gain_deficit_db") is not None
    ]
    deltas = []
    for member in group.members:
        comparison = member.mastering_comparison
        if comparison is None:
            continue
        for name in (
            "active_loudness_delta_db",
            "true_peak_delta_db",
            "plr_delta_db",
            "gain_deficit_delta_db",
        ):
            value = getattr(comparison, name)
            if value is not None:
                deltas.append(abs(value))
    return (
        0 if deficits else 1,
        -(max(deficits) if deficits else 0.0),
        -(max(deltas) if deltas else 0.0),
        group.group_id,
    )


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
        lambda service: {
            "event": "export",
            "status": "succeeded",
            "exports": service.export(facet, type=type_, format=format_, fields=fields),
        },
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

    def report(event: str, index: int, total: int, group: str, source: str, target: str) -> None:
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
    json_output: JsonOption = False,
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
        json_output=json_output,
    )


@app.command()
def doctor(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Check workspace roots, schema migrations, and required binaries."""
    _run(config, lambda service: service.doctor(), json_output=json_output)


@app.command()
def status(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Report source freshness and currently known catalog state."""
    _run(config, lambda service: service.status(), json_output=json_output)


@database_app.command("optimize")
def database_optimize(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Update SQLite planner statistics when useful."""
    _run(config, lambda service: service.optimize_database(), json_output=json_output)


@database_app.command("quick-check")
def database_quick_check(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Run SQLite's lightweight consistency check."""
    _run(config, lambda service: service.quick_check_database(), json_output=json_output)


@database_app.command("integrity-check")
def database_integrity_check(config: ConfigOption, json_output: JsonOption = False) -> None:
    """Run SQLite's explicit full integrity check."""
    _run(config, lambda service: service.integrity_check_database(), json_output=json_output)


@database_app.command("rebuild-current-analysis")
def database_rebuild_current_analysis(
    config: ConfigOption, json_output: JsonOption = False
) -> None:
    """Rebuild the derived latest-successful-analysis projection."""
    _run(config, lambda service: service.rebuild_current_analysis(), json_output=json_output)


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

    def action(service: WorkspaceApplication) -> dict[str, Any]:
        with RichProgressReporter(verbosity=ctx.obj.get("verbosity", 0)) as progress:
            return service.refresh(
                progress=progress,
                workers=workers,
                track_timeout=track_timeout,
            )

    _run(config, action, json_output=json_output)


@app.command()
def jobs(config: ConfigOption, json_output: JsonOption = False) -> None:
    """List background jobs launched with --background and their status."""
    workspace_config = WorkspaceConfig.load(config)
    payload = {
        "event": "jobs",
        "status": "succeeded",
        "jobs": background.list_jobs(workspace_config.database),
    }
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        render(payload)


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
