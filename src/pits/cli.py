"""Command line entry point for the Pits App data platform."""

import typer

from pits import __version__
from pits.normalized.cli import normalize_app
from pits.sources.cli import extract_app
from pits.storage.cli import storage_app
from pits.warehouse.cli import db_app

app = typer.Typer(
    help="Pits App data platform CLI.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)
app.add_typer(storage_app, name="storage")
app.add_typer(extract_app, name="extract")
app.add_typer(normalize_app, name="normalize")
app.add_typer(db_app, name="db")


# Root callback keeps `version` as a subcommand (Typer collapses single-command apps).
@app.callback()
def main() -> None:
    """Pits App data platform CLI."""


@app.command()
def version() -> None:
    """Print the installed package version."""
    typer.echo(__version__)
