"""HydroFound CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(
    name="hydrofound",
    help="Scientific knowledge base — papers, packages, codebases → queryable markdown.",
    no_args_is_help=True,
)

console = Console()


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


from hydrofound.cli.catalog import (  # noqa: E402
    catalog_app,
    export_bibtex_command,
    remove_command,
)
from hydrofound.cli.discover import discover_cmd  # noqa: E402
from hydrofound.cli.doctor import doctor_command  # noqa: E402
from hydrofound.cli.download import download_cmd  # noqa: E402
from hydrofound.cli.ingest import ingest_app  # noqa: E402
from hydrofound.cli.init import init_command  # noqa: E402
from hydrofound.cli.search import search_command  # noqa: E402

app.command(name="init")(init_command)
app.add_typer(ingest_app, name="ingest")
app.command(name="search")(search_command)
app.add_typer(catalog_app, name="catalog")
app.command(name="remove")(remove_command)
app.command(name="discover")(discover_cmd)
app.command(name="download")(download_cmd)
app.command(name="doctor")(doctor_command)
app.command(name="export-bibtex")(export_bibtex_command)


@app.command(name="reindex")
def reindex_command(ctx: typer.Context) -> None:
    """Rebuild catalog from filesystem and regenerate catalog.md."""
    kb_path = ctx.obj.get("kb") if ctx.obj else None
    if not kb_path or not (kb_path / ".hydrofound").exists():
        typer.echo("Error: --kb required and must point to initialized KB", err=True)
        raise typer.Exit(code=1)

    from hydrofound.catalog.index import CatalogIndex
    from hydrofound.catalog.render import render_catalog_md

    # Rebuild catalog.json from frontmatter (filesystem is truth)
    catalog = CatalogIndex.rebuild(kb_path)

    # Regenerate catalog.md
    (kb_path / "catalog.md").write_text(render_catalog_md(catalog.entries))

    # Trigger qmd reindex if available (best-effort)
    from hydrofound.query.qmd import qmd_reindex

    qmd_reindex(kb_path)

    console.print(f"Reindexed: {len(catalog.entries)} entries")


@app.command(name="serve")
def serve_command(
    ctx: typer.Context,
) -> None:
    """Start the MCP server (stdio transport)."""
    import asyncio

    from mcp.server.stdio import stdio_server

    from hydrofound.mcp_server import create_server

    kb_path = ctx.obj.get("kb") if ctx.obj else None
    if not kb_path:
        typer.echo("Error: --kb required for serve command", err=True)
        raise typer.Exit(code=1)

    server = create_server(kb_path)

    async def run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(run())


@app.command(name="fetch")
def fetch_command(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query for papers"),
    limit: int = typer.Option(5, "--limit", "-n", help="Number of papers to find"),
    topic: str = typer.Option(
        "uncategorized", "--topic", "-t", help="Topic for ingested papers"
    ),
    source: str = typer.Option(
        "all", "--source", "-s", help="Search source: all, semantic_scholar, exa"
    ),
    no_ingest: bool = typer.Option(
        False, "--no-ingest", help="Download only, don't ingest"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Discovery only — no download, no ingest. Prints results table.",
    ),
) -> None:
    """Search, download, and ingest papers in one step.

    Combines discover → download → ingest into a single command.
    Only open-access papers with PDF URLs are downloaded.
    """
    import asyncio

    kb_path = ctx.obj.get("kb") if ctx.obj else None
    offline = ctx.obj.get("offline", False)

    if not kb_path or not (kb_path / ".hydrofound").exists():
        console.print(
            "[red]Error:[/red] --kb required and must point to initialized KB"
        )
        raise typer.Exit(code=1)
    if offline:
        console.print(
            "[red]Error:[/red] fetch requires network access (--offline is set)"
        )
        raise typer.Exit(code=1)

    try:
        from hydrofound.config import load_config
        from hydrofound.discovery.orchestrator import discover_papers
        from hydrofound.discovery.providers import build_providers

        config = load_config(kb_path)

        # Step 1: Discover
        console.print(f"Searching for: [bold]{query}[/bold] (limit={limit})")
        providers = build_providers(source, config)
        if not providers:
            console.print("[red]No providers available.[/red] Set API keys first.")
            raise typer.Exit(code=1)

        results = asyncio.run(discover_papers(query, providers, limit=limit))

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            raise typer.Exit(code=0)

        console.print(f"Found {len(results)} result(s)")

        # Dry-run: print results table and exit without download/ingest
        if dry_run:
            from rich.table import Table

            table = Table(
                title="Discovery Results (dry-run)",
                show_header=True,
                header_style="bold",
            )
            table.add_column("Title", style="cyan", max_width=60)
            table.add_column("DOI", style="dim", max_width=30)
            table.add_column("PDF URL", justify="center")
            for r in results:
                pdf_available = "[green]yes[/green]" if r.pdf_url else "[red]no[/red]"
                table.add_row(
                    r.title[:60] if r.title else "(no title)",
                    r.doi or "",
                    pdf_available,
                )
            console.print(table)
            raise typer.Exit(code=0)

        # Step 2: Download papers with PDF URLs
        from hydrofound.discovery.downloader import download_paper
        from hydrofound.discovery.unpaywall import resolve_pdf_url

        pdf_dir = kb_path / "pdfs"
        pdf_dir.mkdir(exist_ok=True)
        downloaded = []

        for r in results:
            # Try to get a PDF URL: provider → Unpaywall fallback
            if not r.pdf_url and r.doi:
                resolved = asyncio.run(resolve_pdf_url(r.doi))
                if resolved:
                    r.pdf_url = resolved

            if not r.pdf_url:
                console.print(f"  [dim]SKIP[/dim] {r.title[:60]} — no PDF URL")
                continue

            try:
                pdf_path = asyncio.run(download_paper(r, pdf_dir))
                if pdf_path:
                    console.print(f"  [green]OK[/green]   {r.title[:60]}")
                    downloaded.append((pdf_path, r))
                else:
                    console.print(
                        f"  [yellow]FAIL[/yellow] {r.title[:60]} — not a valid PDF"
                    )
            except Exception as exc:
                console.print(f"  [yellow]FAIL[/yellow] {r.title[:60]} — {exc}")

        if not downloaded:
            console.print("[yellow]No papers downloaded.[/yellow]")
            raise typer.Exit(code=0)

        console.print(f"\nDownloaded {len(downloaded)} paper(s)")

        if no_ingest:
            console.print("Skipping ingestion (--no-ingest)")
            raise typer.Exit(code=0)

        # Step 3: Ingest
        from hydrofound.ingestion.paper import ingest_paper

        ingested = 0
        for pdf_path, paper_result in downloaded:
            try:
                entry = ingest_paper(pdf_path, topic, kb_path, config, no_reindex=True)
                if entry:
                    console.print(f"  [green]Ingested[/green] {entry.title[:60]}")
                    ingested += 1
                else:
                    console.print("  [dim]Skipped[/dim] (duplicate DOI)")
            except Exception as exc:
                console.print(f"  [red]Failed[/red] {pdf_path.name}: {exc}")

        console.print(
            f"\n[bold]{ingested} paper(s) ingested into topic '{topic}'[/bold]"
        )

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def version() -> None:
    """Print version."""
    from hydrofound import __version__

    typer.echo(f"hydrofound {__version__}")
