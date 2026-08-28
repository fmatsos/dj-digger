from pathlib import Path

from typer.testing import CliRunner

from dj_digger.cli import app
from dj_digger.duplicates.quality import QualityMarkResult
from dj_digger.duplicates.service import (
    DuplicateAnalysisResult,
    DuplicateGroupDescription,
    DuplicateMemberDescription,
)


def _config(tmp_path: Path, *, enabled: bool = True) -> Path:
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
                f"enabled = {'true' if enabled else 'false'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def test_help_describes_duplicates_command() -> None:
    result = CliRunner().invoke(app, ["duplicates", "--help"])

    assert result.exit_code == 0
    assert "--analyze" in result.output
    assert "--list" in result.output
    assert "--mark-best-quality" in result.output


def test_requires_at_least_one_action(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["duplicates", "--config", str(_config(tmp_path))])

    assert result.exit_code == 2
    assert "one of --analyze, --list, or --mark-best-quality is required" in result.output


def test_analyze_and_list_are_mutually_exclusive(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["duplicates", "--analyze", "--list", "--config", str(_config(tmp_path))]
    )

    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_list_and_mark_best_quality_are_mutually_exclusive(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["duplicates", "--list", "--mark-best-quality", "--config", str(_config(tmp_path))],
    )

    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_workers_requires_analyze(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["duplicates", "--list", "--workers", "2", "--config", str(_config(tmp_path))]
    )

    assert result.exit_code == 2
    assert "--workers is only valid with --analyze" in result.output


def test_track_timeout_requires_analyze(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "duplicates",
            "--mark-best-quality",
            "--track-timeout",
            "5",
            "--config",
            str(_config(tmp_path)),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "--track-timeout is only valid with --analyze" in result.output


def test_analyze_propagates_source_and_execution_options(monkeypatch, tmp_path: Path) -> None:
    received: dict[str, object] = {}

    def duplicates_analyze(self, source_id=None, **options):
        received.update(source_id=source_id, **options)
        return DuplicateAnalysisResult(
            files_total=1,
            analyzed=1,
            reused=0,
            failed=0,
            duplicate_files=0,
            duplicate_groups=0,
            elapsed_seconds=0.1,
        )

    monkeypatch.setattr("dj_digger.cli.WorkspaceApplication.duplicates_analyze", duplicates_analyze)

    result = CliRunner().invoke(
        app,
        [
            "duplicates",
            "--analyze",
            "--mark-best-quality",
            "--source",
            "library",
            "--workers",
            "3",
            "--track-timeout",
            "12.5",
            "--config",
            str(_config(tmp_path)),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert received["source_id"] == "library"
    assert received["workers"] == 3
    assert received["track_timeout"] == 12.5
    assert received["mark_best_quality"] is True
    assert '"event":"duplicates"' in result.output
    assert '"status":"succeeded"' in result.output


def test_analyze_uses_safe_execution_defaults(monkeypatch, tmp_path: Path) -> None:
    received: dict[str, object] = {}

    def duplicates_analyze(self, source_id=None, **options):
        received.update(options)
        return DuplicateAnalysisResult(
            files_total=0,
            analyzed=0,
            reused=0,
            failed=0,
            duplicate_files=0,
            duplicate_groups=0,
            elapsed_seconds=0.0,
        )

    monkeypatch.setattr("dj_digger.cli.WorkspaceApplication.duplicates_analyze", duplicates_analyze)

    result = CliRunner().invoke(
        app, ["duplicates", "--analyze", "--config", str(_config(tmp_path)), "--json"]
    )

    assert result.exit_code == 0
    assert received["workers"] == 1
    assert received["track_timeout"] == 1800.0
    assert received["mark_best_quality"] is False


def test_analyze_maps_partial_failure_to_exit_code_two(monkeypatch, tmp_path: Path) -> None:
    def duplicates_analyze(self, source_id=None, **options):
        return DuplicateAnalysisResult(
            files_total=2,
            analyzed=1,
            reused=0,
            failed=1,
            duplicate_files=0,
            duplicate_groups=0,
            elapsed_seconds=0.0,
        )

    monkeypatch.setattr("dj_digger.cli.WorkspaceApplication.duplicates_analyze", duplicates_analyze)

    result = CliRunner().invoke(
        app, ["duplicates", "--analyze", "--config", str(_config(tmp_path)), "--json"]
    )

    assert result.exit_code == 2
    assert '"status":"partial"' in result.output


def test_list_emits_ordered_groups_with_members_and_quality_state(
    monkeypatch, tmp_path: Path
) -> None:
    def duplicates_list(self, source_id=None):
        return [
            DuplicateGroupDescription(
                group_id="hash-1",
                members=(
                    DuplicateMemberDescription(
                        source_id="library",
                        track_id=1,
                        relative_path="A.flac",
                        technical_facts={"lossless": True},
                        best_quality=True,
                    ),
                    DuplicateMemberDescription(
                        source_id="library",
                        track_id=2,
                        relative_path="A.mp3",
                        technical_facts={"lossless": False},
                        best_quality=False,
                    ),
                ),
            )
        ]

    monkeypatch.setattr("dj_digger.cli.WorkspaceApplication.duplicates_list", duplicates_list)

    result = CliRunner().invoke(
        app, ["duplicates", "--list", "--config", str(_config(tmp_path)), "--json"]
    )

    assert result.exit_code == 0
    assert '"group_id":"hash-1"' in result.output
    assert '"track_id":1' in result.output
    assert '"best_quality":true' in result.output
    assert '"best_quality":false' in result.output


def test_mark_best_quality_reports_failed_status_and_exit_code(monkeypatch, tmp_path: Path) -> None:
    def duplicates_mark_best_quality(self, source_id=None):
        return QualityMarkResult(status="failed", marked_best=0, incomplete_track_ids=(3, 5))

    monkeypatch.setattr(
        "dj_digger.cli.WorkspaceApplication.duplicates_mark_best_quality",
        duplicates_mark_best_quality,
    )

    result = CliRunner().invoke(
        app,
        ["duplicates", "--mark-best-quality", "--config", str(_config(tmp_path)), "--json"],
    )

    assert result.exit_code == 1
    assert '"incomplete_track_ids":[3,5]' in result.output


def test_unknown_or_disabled_source_fails(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "duplicates",
            "--list",
            "--source",
            "missing",
            "--config",
            str(_config(tmp_path)),
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert '"status":"failed"' in result.output


def test_disabled_source_is_rejected(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "duplicates",
            "--list",
            "--source",
            "library",
            "--config",
            str(_config(tmp_path, enabled=False)),
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert '"status":"failed"' in result.output
