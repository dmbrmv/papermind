"""papermind search CLI command — query the knowledge base."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def search_command(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query (space-separated terms)."),
    scope: str = typer.Option(
        None,
        "--scope",
        help="Restrict search to a content type (papers/packages/codebases).",
    ),
    topic: str = typer.Option(
        None,
        "--topic",
        "-t",
        help="Filter results to a specific topic (e.g. 'swat_ml').",
    ),
    year: int = typer.Option(
        None,
        "--year",
        "-y",
        help="Only papers from this year onward (e.g. --year 2020).",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        min=1,
        max=200,
        help="Maximum number of results to return.",
    ),
) -> None:
    """Search the knowledge base.

    Uses qmd if available, otherwise falls back to built-in grep-based search.
    """
    kb: Path | None = ctx.obj.get("kb") if ctx.obj else None
    if kb is None:
        console.print(
            "[red]No knowledge base specified.[/red] "
            "Pass [bold]--kb <path>[/bold] or run from within a KB directory."
        )
        raise typer.Exit(code=1)
    if not kb.is_dir():
        console.print(f"[red]KB directory not found:[/red] {kb}")
        raise typer.Exit(code=1)

    # Prefer qmd if available (semantic search) — fallback if not.
    from papermind.query.qmd import is_qmd_available, qmd_search

    # Build scope from --scope and --topic
    effective_scope = scope or ""
    if topic and not effective_scope:
        effective_scope = f"papers/{topic}"
    elif topic and effective_scope == "papers":
        effective_scope = f"papers/{topic}"

    if is_qmd_available():
        try:
            results = qmd_search(kb, query, scope=effective_scope, limit=limit)
        except RuntimeError:
            results = []

        if results:
            _print_results_table(query, results)
            return

        # qmd returned nothing — try fallback before giving up
        console.print("[dim]qmd: no results, trying fallback...[/dim]")

    _run_fallback_search(kb, query, scope=effective_scope, year_from=year, limit=limit)


def _print_results_table(query: str, results: list) -> None:
    """Render a Rich table for a list of SearchResult objects.

    Args:
        query: The original query string (used in the table title).
        results: Non-empty list of SearchResult instances.
    """
    table = Table(
        title=f'Search results for "{query}"',
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Title", style="bold", no_wrap=False, ratio=2)
    table.add_column("Path", style="dim", no_wrap=False, ratio=3)
    table.add_column("Score", justify="right", style="green", no_wrap=True, ratio=1)
    table.add_column("Snippet", no_wrap=False, ratio=5)

    for r in results:
        table.add_row(r.title, r.path, f"{r.score:.1f}", r.snippet[:180] if r.snippet else "")

    console.print(table)
    console.print(f"[dim]{len(results)} result(s)[/dim]")


def _run_fallback_search(
    kb: Path,
    query: str,
    *,
    scope: str | None,
    year_from: int | None = None,
    limit: int,
) -> None:
    """Run built-in grep-based fallback search and pretty-print results.

    Args:
        kb: Path to the knowledge base root.
        query: Search query string.
        scope: Optional scope filter.
        year_from: Only include papers from this year onward.
        limit: Maximum results.
    """
    from papermind.query.fallback import fallback_search

    results = fallback_search(kb, query, scope=scope, year_from=year_from, limit=limit)

    if not results:
        console.print(f"[yellow]No results found for:[/yellow] {query!r}")
        return

    _print_results_table(query, results)
