"""Command-line interface for DJ Digger."""

import typer

app = typer.Typer(help="Catalog and export DJ music libraries.")


@app.callback()
def callback() -> None:
    """DJ Digger command-line application."""


def main() -> None:
    """Run the DJ Digger command-line application."""
    app()


if __name__ == "__main__":
    main()
