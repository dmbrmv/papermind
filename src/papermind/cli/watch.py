"""papermind watch — surface relevant KB entries for a source file."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def watch_cmd(
    ctx: typer.Context,
    file: Path = typer.Argument(..., help="Source file to analyze"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results"),
) -> None:
    """Surface relevant KB entries for a source code file.

    Parses the file to extract concepts (imports, class/function names,
    docstrings), then searches the KB for matching papers, packages,
    and codebases.

    Examples::

        papermind watch src/hydrohub/swat_diff/models/groundwater.py
        papermind watch calibration/optuna_optimizer.py --limit 3
    """
    from papermind.watch import check_pitfalls, format_watch_output, watch_file

    kb = _resolve_kb(ctx)
    resolved = file.resolve()

    if not resolved.exists():
        console.print(f"[red]File not found:[/red] {resolved}")
        raise typer.Exit(code=1)

    results = watch_file(resolved, kb, limit=limit)
    pitfalls = check_pitfalls(resolved, kb)
    output = format_watch_output(resolved.name, results, pitfalls)
    typer.echo(output)
