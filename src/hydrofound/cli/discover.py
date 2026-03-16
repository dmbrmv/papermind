"""hydrofound discover CLI command — find papers from academic search APIs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from hydrofound.config import HydroFoundConfig

console = Console()

app = typer.Typer(help="Discover papers from academic search APIs.")


@app.command(name="discover")
def discover_cmd(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results per provider"),
    source: str = typer.Option(
        "all",
        "--source",
        "-s",
        help="Provider: all, semantic_scholar, exa",
    ),
) -> None:
    """Discover papers from academic search APIs.

    Queries one or more search providers in parallel, deduplicates the
    combined results, pretty-prints them, and caches them to
    ``kb/.hydrofound/last_search.json`` for use by the download command.
    """
    from hydrofound.config import load_config
    from hydrofound.discovery.orchestrator import discover_papers

    offline: bool = ctx.obj.get("offline", False) if ctx.obj else False
    if offline:
        typer.echo("Error: Offline mode: discover requires network access", err=True)
        raise typer.Exit(code=1)

    kb: Path | None = ctx.obj.get("kb") if ctx.obj else None
    if kb is None:
        console.print(
            "[red]No knowledge base specified.[/red] "
            "Pass [bold]--kb <path>[/bold] or run from within a KB directory."
        )
        raise typer.Exit(code=1)

    cfg = load_config(kb)

    providers = _build_providers(source, cfg)
    if not providers:
        console.print(
            "[red]No providers available.[/red] "
            "Configure API keys via env vars or .hydrofound/config.toml."
        )
        raise typer.Exit(code=1)

    provider_names = ", ".join(p.name for p in providers)
    console.print(f"[dim]Searching via: {provider_names}[/dim]")

    results = asyncio.run(discover_papers(query, providers, limit=limit))

    if not results:
        console.print(f"[yellow]No results found for:[/yellow] {query!r}")
        raise typer.Exit(code=0)

    _print_results(query, results)
    _cache_results(kb, query, results)


def _build_providers(source: str, cfg: HydroFoundConfig) -> list:
    """Build provider list based on --source flag and available API keys."""
    from hydrofound.discovery.providers import build_providers

    providers = build_providers(source, cfg)
    if source in ("all", "exa") and not cfg.exa_key:
        console.print(
            "[yellow]Exa provider skipped:[/yellow] "
            "set HYDROFOUND_EXA_KEY or exa_key in config.toml."
        )
    return providers


def _print_results(query: str, results: list) -> None:
    """Render search results as a Rich table.

    Args:
        query: Original search query (used in table title).
        results: List of :class:`PaperResult` objects.
    """
    table = Table(
        title=f'Discover results for "{query}"',
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("#", style="dim", no_wrap=True, ratio=1)
    table.add_column("Title", style="bold", no_wrap=False, ratio=4)
    table.add_column("Year", justify="right", no_wrap=True, ratio=1)
    table.add_column("Source", style="dim", no_wrap=True, ratio=1)
    table.add_column("DOI / URL", style="blue", no_wrap=False, ratio=3)

    for idx, r in enumerate(results, start=1):
        identifier = r.doi or r.pdf_url or ""
        table.add_row(
            str(idx),
            r.title,
            str(r.year) if r.year else "—",
            r.source,
            identifier,
        )

    console.print(table)
    console.print(f"[dim]{len(results)} result(s)[/dim]")


def _cache_results(kb: Path, query: str, results: list) -> None:
    """Persist results to ``kb/.hydrofound/last_search.json``.

    Args:
        kb: Path to the knowledge base root.
        query: Search query string (stored alongside results).
        results: List of :class:`PaperResult` objects to serialise.
    """
    cache_dir = kb / ".hydrofound"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "last_search.json"

    payload = {
        "query": query,
        "results": [
            {
                "title": r.title,
                "authors": r.authors,
                "year": r.year,
                "doi": r.doi,
                "abstract": r.abstract,
                "pdf_url": r.pdf_url,
                "source": r.source,
                "is_open_access": r.is_open_access,
                "venue": r.venue,
                "citation_count": r.citation_count,
            }
            for r in results
        ],
    }

    cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    console.print(f"[dim]Cached to {cache_file}[/dim]")
