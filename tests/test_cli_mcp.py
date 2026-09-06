from pathlib import Path

from typer.testing import CliRunner

from dj_digger.cli import app


def test_mcp_help_describes_its_bounded_write_surface() -> None:
    result = CliRunner().invoke(app, ["mcp", "--help"])

    assert result.exit_code == 0
    assert "draft creation" in result.stdout
    assert "read-only" not in result.stdout


def test_mcp_missing_catalog_fails_on_stderr_without_protocol_output(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '[workspace]\ndatabase = "missing.sqlite"\nexports = "exports"\n'
        "\n[library]\nsources = []\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["mcp", "--config", str(config)])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "MCP startup failed" in result.stderr
    assert "missing.sqlite" not in result.stderr
