"""HydroFound CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(
    name="hydrofound",
    help="Scientific knowledge base — papers, packages, codebases → queryable markdown.",
    no_args_is_help=True,
)


def kb_path_option(value: str | None = None) -> Path | None:
    """Resolve --kb option to a Path."""
    if value is None:
        return None
    return Path(value).resolve()


@app.callback()
def main_callback(
    ctx: typer.Context,
    kb: str = typer.Option(None, "--kb", help="Path to HydroFound knowledge base"),
    offline: bool = typer.Option(False, "--offline", help="Disable all network access"),
) -> None:
    """Global options."""
    ctx.ensure_object(dict)
    ctx.obj["kb"] = Path(kb).resolve() if kb else None
    ctx.obj["offline"] = offline


from hydrofound.cli.init import init_command  # noqa: E402

app.command(name="init")(init_command)


@app.command()
def version() -> None:
    """Print version."""
    from hydrofound import __version__

    typer.echo(f"hydrofound {__version__}")
