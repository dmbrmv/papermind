"""papermind profile CLI — auto-generate codebase summaries."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def profile_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(".", help="Codebase root directory."),
) -> None:
    """Generate a project profile from codebase analysis.

    Walks the codebase to extract language stats, function/class counts,
    # REF: annotations, and inferred topics. Useful for understanding
    a project's scope and its connections to the knowledge base.

    Examples::

        papermind profile .
        papermind profile ~/Development/HydroHub/src
    """
    from papermind.profile import format_profile, generate_profile

    resolved = path.resolve()
    if not resolved.is_dir():
        console.print(f"[red]Not a directory:[/red] {resolved}")
        raise typer.Exit(code=1)

    kb_path = ctx.obj.get("kb") if ctx.obj else None
    if not kb_path:
        try:
            kb_path = _resolve_kb(ctx)
        except (typer.Exit, SystemExit):
            kb_path = None

    profile = generate_profile(resolved, kb_path)
    console.print(format_profile(profile))
