"""Shared CLI utilities for papermind commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

console = Console()


def _resolve_kb(ctx: typer.Context) -> Path:
    """Resolve the KB path from context or raise an error.

    Args:
        ctx: Typer context carrying ``kb`` in ``ctx.obj``.

    Returns:
        Resolved knowledge base path.

    Raises:
        typer.Exit: With code 1 if no KB is set or the path is not a valid KB.
    """
    kb: Path | None = ctx.obj.get("kb") if ctx.obj else None
    if kb is None:
        console.print(
            "[red]No knowledge base specified.[/red] "
            "Pass --kb <path> or run from within a KB directory."
        )
        raise typer.Exit(code=1)
    if not (kb / ".papermind").exists():
        console.print(
            f"[red]Not a valid PaperMind KB:[/red] {kb}\n"
            "Run [bold]papermind init[/bold] to create one."
        )
        raise typer.Exit(code=1)
    return kb
