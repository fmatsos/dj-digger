"""End-to-end scan history behaviour through the public CLI."""

import os
from pathlib import Path

from typer.testing import CliRunner

from dj_digger.catalog.database import Database
from dj_digger.cli import app


def write_config(path: Path, source: Path) -> Path:
    config = path / "dj-digger.toml"
    config.write_text(
        "\n".join(
            [
                "[workspace]",
                'database = "catalog.sqlite"',
                'exports = "exports"',
                "",
                "[[library.sources]]",
                'id = "library"',
                f'path = "{source}"',
                "set_eligible = true",
                "analyze = false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def scan(runner: CliRunner, config: Path) -> object:
    return runner.invoke(app, ["scan", "--config", str(config)])


def test_scan_failure_missing_and_restoration_keep_a_complete_history(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "library"
    source.mkdir()
    first = source / "A.flac"
    second = source / "B.flac"
    first.write_bytes(b"audio A")
    second.write_bytes(b"audio B")
    config = write_config(tmp_path, source)
    runner = CliRunner()

    assert scan(runner, config).exit_code == 0

    second.unlink()
    interrupted = source / "interrupted"
    interrupted.mkdir()
    original_scandir = os.scandir

    def fail_after_observing_a(path: str | bytes | os.PathLike[str] | os.PathLike[bytes]):
        if Path(path) == interrupted:
            raise OSError("traversal interrupted")
        return original_scandir(path)

    monkeypatch.setattr("dj_digger.scanning.scanner.os.scandir", fail_after_observing_a)
    first_failure = scan(runner, config)
    second_failure = scan(runner, config)

    assert first_failure.exit_code != 0
    assert second_failure.exit_code != 0
    assert '"status":"failed"' in first_failure.output
    assert '"status":"failed"' in second_failure.output

    database = Database.open(tmp_path / "catalog.sqlite")
    assert (
        database.scalar("SELECT presence_status FROM tracks WHERE relative_path = 'B.flac'")
        == "present"
    )
    assert database.execute("SELECT status FROM scan_runs ORDER BY id").fetchall() == [
        ("succeeded",),
        ("failed",),
        ("failed",),
    ]

    monkeypatch.setattr("dj_digger.scanning.scanner.os.scandir", original_scandir)
    assert scan(runner, config).exit_code == 0
    assert (
        database.scalar("SELECT presence_status FROM tracks WHERE relative_path = 'B.flac'")
        == "missing"
    )

    second.write_bytes(b"audio B")
    assert scan(runner, config).exit_code == 0
    assert database.execute(
        "SELECT event_type FROM track_events "
        "WHERE track_id = (SELECT id FROM tracks WHERE relative_path = 'B.flac') "
        "AND event_type IN ('missing', 'restored') ORDER BY id"
    ).fetchall() == [("missing",), ("restored",)]
