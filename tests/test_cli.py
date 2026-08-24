from typer.testing import CliRunner

from dj_digger.cli import app


def test_help_exits_successfully_and_describes_the_application() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Catalog and export DJ music libraries." in result.output
