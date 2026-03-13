"""hydrofound search CLI command — query the knowledge base."""

from __future__ import annotations

import shutil
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
        help="Restrict search to a top-level KB subdirectory (papers/packages/codebases).",
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
    if shutil.which("qmd") is not None:
        _run_qmd_search(kb, query, scope=scope, limit=limit)
    else:
        _run_fallback_search(kb, query, scope=scope, limit=limit)


def _run_qmd_search(
    kb: Path,
    query: str,
    *,
    scope: str | None,
    limit: int,
) -> None:
    """Delegate to qmd for semantic search.

    Args:
        kb: Path to the knowledge base root.
        query: Search query string.
        scope: Optional scope filter.
        limit: Maximum results.
    """
    import subprocess

    cmd = ["qmd", "search", str(kb), query, f"--limit={limit}"]
    if scope:
        cmd.append(f"--scope={scope}")

    result = subprocess.run(cmd, capture_output=False)  # noqa: S603
    raise typer.Exit(code=result.returncode)


def _run_fallback_search(
    kb: Path,
    query: str,
    *,
    scope: str | None,
    limit: int,
) -> None:
    """Run built-in grep-based fallback search and pretty-print results.

    Args:
        kb: Path to the knowledge base root.
        query: Search query string.
        scope: Optional scope filter.
        limit: Maximum results.
    """
    from hydrofound.query.fallback import fallback_search

    results = fallback_search(kb, query, scope=scope, limit=limit)

    if not results:
        console.print(f"[yellow]No results found for:[/yellow] {query!r}")
        return

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
        table.add_row(r.title, r.path, f"{r.score:.1f}", r.snippet[:180])

    console.print(table)
    console.print(f"[dim]{len(results)} result(s)[/dim]")
