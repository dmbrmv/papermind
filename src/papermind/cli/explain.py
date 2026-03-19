"""papermind explain CLI — concept / parameter glossary lookup."""

from __future__ import annotations

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def explain_cmd(
    ctx: typer.Context,
    concept: str = typer.Argument(..., help="Parameter name or concept to explain."),
) -> None:
    """Explain a hydrological parameter or concept.

    Looks up the concept in a curated glossary first, then falls back to
    searching the knowledge base.  Returns a structured definition with
    typical range, units, and key reference.

    Examples::

        papermind explain CN2
        papermind explain "baseflow"
        papermind explain KGE
    """
    from papermind.explain import explain, format_explain

    kb_path = ctx.obj.get("kb") if ctx.obj else None
    if not kb_path:
        try:
            kb_path = _resolve_kb(ctx)
        except (typer.Exit, SystemExit):
            kb_path = None

    result = explain(concept, kb_path=kb_path)

    if result is None:
        console.print(
            f"[yellow]No explanation found for[/yellow] [bold]{concept}[/bold].\n"
            "Try a different spelling or add it to glossary.yaml."
        )
        raise typer.Exit(code=1)

    console.print(format_explain(result))
