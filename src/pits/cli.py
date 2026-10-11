"""Command line entry point for the Pits App data platform."""

import typer

from pits import __version__
from pits.storage.cli import storage_app

app = typer.Typer(
    help="Pits App data platform CLI.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(storage_app, name="storage")


# Root callback keeps `version` as a subcommand (Typer collapses single-command apps).
@app.callback()
def main() -> None:
    """Pits App data platform CLI."""


@app.command()
def version() -> None:
    """Print the installed package version."""
    typer.echo(__version__)
