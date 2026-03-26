"""papermind download CLI — download PDFs from discovery results."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def download_cmd(
    ctx: typer.Context,
    query: str = typer.Argument(
        None, help="Search query (or omit to use last results)"
    ),
    from_results: str = typer.Option(
        "",
        "--from-results",
        help="Use 'last' to download from cached last_search.json results.",
    ),
    pick: str = typer.Option(
        "",
        "--pick",
        help="Comma-separated 1-based indices to download, e.g. '1,3,5'.",
    ),
    auto_open_access: bool = typer.Option(
        False,
        "--auto-open-access",
        help="Only download open-access papers.",
    ),
    no_ingest: bool = typer.Option(
        False,
        "--no-ingest",
        help="Download only — skip auto-ingestion into the knowledge base.",
    ),
    topic: str = typer.Option(
        "uncategorized",
        "--topic",
        "-t",
        help="Topic for auto-ingestion (ignored when --no-ingest is set).",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        help="Max results to search when *query* is provided.",
    ),
) -> None:
    """Download papers from discovery results or a new search query.

    If *query* is given and ``--from-results`` is not set, a fresh discovery
    search is run first and the results are cached.  Pass ``--from-results last``
    to skip the search and use the last cached results directly.

    Examples::

        # Search and download all open-access results
        papermind --kb ./kb download "SWAT+ hydrological model" --auto-open-access

        # Download papers #1 and #3 from the last search
        papermind --kb ./kb download --from-results last --pick 1,3

        # Download without ingesting into the KB
        papermind --kb ./kb download "evapotranspiration" --no-ingest
    """
    from papermind.discovery.downloader import (
        pick_results,
    )

    offline: bool = ctx.obj.get("offline", False) if ctx.obj else False
    if offline:
        typer.echo("Error: Offline mode: download requires network access", err=True)
        raise typer.Exit(code=1)

    kb = _resolve_kb(ctx)
    output_dir = kb / "pdfs"

    # ── Resolve paper list ────────────────────────────────────────────────────
    results = _resolve_results(ctx, kb, query, from_results, limit)

    if not results:
        console.print("[yellow]No results to download.[/yellow]")
        raise typer.Exit(code=0)

    # ── Apply filters ─────────────────────────────────────────────────────────
    if pick:
        results = pick_results(results, pick)
        if not results:
            console.print(f"[red]No results matched pick indices:[/red] {pick!r}")
            raise typer.Exit(code=1)

    if auto_open_access:
        results = [r for r in results if r.is_open_access]
        if not results:
            console.print("[yellow]No open-access papers in results.[/yellow]")
            raise typer.Exit(code=0)

    console.print(f"[dim]Downloading {len(results)} paper(s) → {output_dir}[/dim]")

    # ── Download loop ─────────────────────────────────────────────────────────
    downloaded: list[Path] = asyncio.run(_download_all(results, output_dir))

    # ── Optional auto-ingest ──────────────────────────────────────────────────
    if not no_ingest and downloaded:
        _auto_ingest(ctx, downloaded, topic, kb)


async def _download_all(results: list, output_dir: Path) -> list[Path]:
    """Download all papers, reporting per-item success/failure.

    Args:
        results: List of :class:`PaperResult` objects.
        output_dir: Target directory for downloaded PDFs.

    Returns:
        List of paths for successfully downloaded files.
    """
    from papermind.discovery.downloader import download_paper

    downloaded: list[tuple[Path, object]] = []
    for r in results:
        label = (r.title or r.doi or r.pdf_url or "unknown")[:60]
        if not r.pdf_url:
            console.print(f"  [yellow]SKIP[/yellow] {label!r} — no PDF URL")
            continue

        dest = await download_paper(r, output_dir)
        if dest is not None:
            console.print(f"  [green]OK[/green]   {label!r} → {dest.name}")
            downloaded.append((dest, r))
        else:
            console.print(
                f"  [red]FAIL[/red] {label!r} — download error (404/timeout/not a PDF)"
            )

    console.print(
        f"[bold]{len(downloaded)}[/bold] / {len(results)} downloaded successfully."
    )
    return downloaded


def _resolve_results(
    ctx: typer.Context,
    kb: Path,
    query: str | None,
    from_results: str,
    limit: int,
) -> list:
    """Return the list of PaperResult to work with.

    Loads from cache when ``from_results == 'last'``, otherwise runs a fresh
    search using the provided *query*.

    Args:
        ctx: Typer context (carries KB path and config).
        kb: Resolved knowledge base path.
        query: Optional search query string.
        from_results: ``'last'`` to load from cache; anything else triggers a
            fresh search (requires *query*).
        limit: Max results per provider for fresh searches.

    Returns:
        List of :class:`PaperResult` objects ready for filtering/downloading.
    """
    from papermind.discovery.downloader import load_last_search

    if from_results.lower() == "last":
        results = load_last_search(kb)
        if not results:
            console.print(
                "[yellow]No cached results found.[/yellow] "
                "Run [bold]papermind discover[/bold] first, or provide a query."
            )
        else:
            console.print(f"[dim]Loaded {len(results)} cached result(s).[/dim]")
        return results

    if query:
        return _run_fresh_search(ctx, kb, query, limit)

    # Neither --from-results last nor a query — load cache with a hint
    results = load_last_search(kb)
    if results:
        console.print(
            f"[dim]No query given — using {len(results)} cached result(s). "
            "Pass --from-results last to silence this hint.[/dim]"
        )
        return results

    console.print(
        "[red]No query and no cached results.[/red] "
        "Provide a search query or run [bold]papermind discover[/bold] first."
    )
    return []


def _run_fresh_search(
    ctx: typer.Context,
    kb: Path,
    query: str,
    limit: int,
) -> list:
    """Execute a discovery search and return the results.

    Mirrors the provider-building logic from ``papermind discover``.

    Args:
        ctx: Typer context.
        kb: Knowledge base root.
        query: Search query string.
        limit: Max results per provider.

    Returns:
        List of :class:`PaperResult` objects from the search.
    """
    from papermind.config import load_config
    from papermind.discovery.orchestrator import discover_papers
    from papermind.discovery.providers import build_providers

    cfg = load_config(kb)
    providers = build_providers("all", cfg)

    console.print(f"[dim]Searching for {query!r} …[/dim]")
    results = asyncio.run(discover_papers(query, providers, limit=limit))
    console.print(f"[dim]Found {len(results)} result(s).[/dim]")
    return results


def _auto_ingest(
    ctx: typer.Context,
    paths: list[tuple[Path, object]],
    topic: str,
    kb: Path,
) -> None:
    """Ingest downloaded PDFs into the knowledge base.

    Failures are reported per-file and do not abort the loop.

    Args:
        ctx: Typer context.
        paths: List of downloaded PDF paths.
        topic: Topic category for the ingested papers.
        kb: Knowledge base root path.
    """
    from papermind.config import load_config
    from papermind.ingestion.paper import ingest_paper

    cfg = load_config(kb)
    console.print(f"[dim]Auto-ingesting {len(paths)} file(s)…[/dim]")
    ingested = 0

    for pdf_path, paper_result in paths:
        try:
            entry = ingest_paper(
                pdf_path,
                topic,
                kb,
                cfg,
                no_reindex=True,
                preferred_title=paper_result.title,
                preferred_doi=paper_result.doi,
                preferred_year=paper_result.year,
                abstract=paper_result.abstract,
                cites=paper_result.cites or None,
                cited_by=paper_result.cited_by or None,
            )
            if entry is None:
                console.print(
                    f"  [yellow]SKIP[/yellow] {pdf_path.name} — duplicate DOI"
                )
            else:
                console.print(f"  [green]INGESTED[/green] {pdf_path.name} → {entry.id}")
                ingested += 1
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [red]INGEST ERROR[/red] {pdf_path.name}: {exc}")

    if ingested:
        from papermind.query.qmd import qmd_reindex

        qmd_reindex(kb)
