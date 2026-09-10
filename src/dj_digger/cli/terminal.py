"""Deterministic, terminal-friendly rendering for command diagnostics."""

import json
from collections.abc import Mapping
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def render(diagnostic: Mapping[str, Any]) -> None:
    event = str(diagnostic.get("event", "command"))
    status = str(diagnostic.get("status", "unknown"))
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="cyan", no_wrap=True)
    table.add_column()
    for key, value in diagnostic.items():
        if key in {"event", "status"}:
            continue
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
        else:
            value_text = str(value)
        table.add_row(key, value_text)
    Console().print(Panel(table, title=f"{event} · {status}", expand=False))


def emit_json(payload: Mapping[str, Any]) -> None:
    """Emit one compact machine-readable payload."""
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def emit(payload: Mapping[str, Any], *, json_output: bool) -> None:
    """Emit one payload in the format the caller selected."""
    if json_output:
        emit_json(payload)
    else:
        render(payload)


__all__ = ["emit", "emit_json", "render"]
