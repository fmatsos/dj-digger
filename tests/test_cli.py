from typer.testing import CliRunner

from dj_digger.cli import app


def test_help_exits_successfully_and_describes_the_application() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Catalog and export DJ music libraries." in result.output


def test_no_command_displays_help_and_available_commands() -> None:
    result = CliRunner().invoke(app)

    assert result.exit_code == 0
    assert "Catalog and export DJ music libraries." in result.output
    assert "Commands" in result.output
    assert "analyze" in result.output
    assert "refresh" in result.output
