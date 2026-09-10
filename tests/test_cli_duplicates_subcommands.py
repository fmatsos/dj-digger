"""Duplicate workflows are subcommands; the legacy flag form still works."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dj_digger.cli import app
from dj_digger.core.duplicates.quality import QualityMarkResult
from dj_digger.core.duplicates.service import DuplicateAnalysisResult


def _config(tmp_path: Path) -> Path:
    source = tmp_path / "music"
    source.mkdir(exist_ok=True)
    config = tmp_path / "dj-digger.toml"
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


def test_help_lists_one_subcommand_per_workflow() -> None:
    result = CliRunner().invoke(app, ["duplicates", "--help"])

    assert result.exit_code == 0
    for name in ("analyze", "list", "mark-best-quality"):
        assert name in result.stdout


@pytest.mark.parametrize(
    ("subcommand", "rejected"),
    [
        ("list", "--workers"),
        ("list", "--mastering"),
        ("mark-best-quality", "--dj-review"),
        ("mark-best-quality", "--background"),
    ],
)
def test_an_option_that_does_not_apply_is_not_offered_at_all(
    tmp_path: Path, subcommand: str, rejected: str
) -> None:
    """Subcommands make the seven hand-written exclusivity checks unnecessary."""
    result = CliRunner().invoke(
        app, ["duplicates", subcommand, "--config", str(_config(tmp_path)), rejected]
    )

    assert result.exit_code == 2
    assert "No such option" in result.output or "Got unexpected" in result.output


def test_analyze_subcommand_runs_the_analysis_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    received: list[object] = []

    def duplicates_analyze(self, request, *, progress=None):
        received.append(request)
        return DuplicateAnalysisResult(
            files_total=1,
            analyzed=1,
            reused=0,
            failed=0,
            duplicate_files=0,
            duplicate_groups=0,
            elapsed_seconds=0.0,
        )

    monkeypatch.setattr(
        "dj_digger.core.application.app.CoreApplication.duplicates_analyze", duplicates_analyze
    )

    result = CliRunner().invoke(
        app,
        [
            "duplicates",
            "analyze",
            "--config",
            str(_config(tmp_path)),
            "--source",
            "library",
            "--workers",
            "3",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout.strip().splitlines()[-1])["event"] == "duplicates"
    assert received[0].source_id == "library"
    assert received[0].workers == 3


def test_mark_best_quality_subcommand_runs_its_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dj_digger.core.application.app.CoreApplication.duplicates_mark_best_quality",
        lambda self, request: QualityMarkResult(status="succeeded", marked_best=2),
    )

    result = CliRunner().invoke(
        app, ["duplicates", "mark-best-quality", "--config", str(_config(tmp_path)), "--json"]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout.strip().splitlines()[-1])["status"] == "succeeded"


def test_parent_config_is_forwarded_to_the_selected_subcommand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    monkeypatch.chdir(tmp_path / "music")

    result = CliRunner().invoke(app, ["duplicates", "--config", str(config), "list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout.strip().splitlines()[-1])["status"] == "succeeded"


def test_the_legacy_flag_form_still_works_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Existing scripts must keep working while the flag form is retired."""
    monkeypatch.setattr(
        "dj_digger.core.application.app.CoreApplication.duplicates_mark_best_quality",
        lambda self, request: QualityMarkResult(status="succeeded", marked_best=0),
    )

    with caplog.at_level("WARNING", logger="dj_digger"):
        result = CliRunner().invoke(
            app,
            [
                "duplicates",
                "--config",
                str(_config(tmp_path)),
                "--mark-best-quality",
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert "deprecated" in caplog.text.lower()
    assert "duplicates mark-best-quality" in caplog.text
