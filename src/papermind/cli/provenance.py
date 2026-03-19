"""papermind provenance CLI — code-to-paper reference management."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()

provenance_app = typer.Typer(
    name="provenance",
    help="Code-to-paper provenance annotations.",
    no_args_is_help=True,
)


@provenance_app.command(name="show")
def provenance_show(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Path to source file."),
) -> None:
    """Show all # REF: annotations in a source file.

    Examples::

        papermind provenance show src/model/water_balance.py
    """
    from papermind.provenance import extract_provenance, format_provenance

    resolved = path.resolve()
    if not resolved.is_file():
        console.print(f"[red]Not a file:[/red] {resolved}")
        raise typer.Exit(code=1)

    refs = extract_provenance(resolved)
    console.print(format_provenance(refs))


@provenance_app.command(name="scan")
def provenance_scan(
    ctx: typer.Context,
    path: Path = typer.Argument(".", help="Codebase root directory."),
) -> None:
    """Scan an entire codebase for # REF: annotations.

    Examples::

        papermind provenance scan .
        papermind provenance scan ~/Development/HydroHub/src
    """
    from papermind.provenance import format_summary, scan_codebase_provenance

    resolved = path.resolve()
    if not resolved.is_dir():
        console.print(f"[red]Not a directory:[/red] {resolved}")
        raise typer.Exit(code=1)

    summary = scan_codebase_provenance(resolved)
    console.print(format_summary(summary))


@provenance_app.command(name="suggest")
def provenance_suggest(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Source file to suggest annotations for."),
    limit: int = typer.Option(5, "--limit", "-n", help="Max suggestions."),
) -> None:
    """Auto-propose # REF: annotations for a source file.

    Extracts concepts from the file and searches the KB for matching
    papers. Prints suggested annotations that could be added.

    Examples::

        papermind provenance suggest src/model/water_balance.py
    """
    from papermind.provenance import suggest_annotations

    kb_path = _resolve_kb(ctx)
    resolved = path.resolve()

    if not resolved.is_file():
        console.print(f"[red]Not a file:[/red] {resolved}")
        raise typer.Exit(code=1)

    suggestions = suggest_annotations(resolved, kb_path, limit=limit)

    if not suggestions:
        console.print("[yellow]No suggestions found.[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"[bold]{len(suggestions)} suggestion(s):[/bold]\n")
    for s in suggestions:
        console.print(f"  [cyan]{s['paper_title']}[/cyan]")
        console.print(f"    {s['annotation']}")
        if s.get("target_functions"):
            fns = ", ".join(
                f"{f['name']} (L{f['line']})" for f in s["target_functions"]
            )
            console.print(f"    [dim]Target functions: {fns}[/dim]")
        console.print()
