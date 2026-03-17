"""PaperMind CLI entry point."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from papermind.config import PaperMindConfig
from rich.console import Console

app = typer.Typer(
    name="papermind",
    help="Scientific knowledge base — papers, packages, codebases.",
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
    kb: str = typer.Option(None, "--kb", help="Path to PaperMind knowledge base"),
    offline: bool = typer.Option(False, "--offline", help="Disable all network access"),
) -> None:
    """Global options."""
    ctx.ensure_object(dict)
    ctx.obj["kb"] = Path(kb).resolve() if kb else None
    ctx.obj["offline"] = offline


from papermind.cli.catalog import (  # noqa: E402
    catalog_app,
    export_bibtex_command,
    remove_command,
)
from papermind.cli.discover import discover_cmd  # noqa: E402
from papermind.cli.doctor import doctor_command  # noqa: E402
from papermind.cli.download import download_cmd  # noqa: E402
from papermind.cli.ingest import ingest_app  # noqa: E402
from papermind.cli.init import init_command  # noqa: E402
from papermind.cli.related import related_cmd  # noqa: E402
from papermind.cli.search import search_command  # noqa: E402

app.command(name="init")(init_command)
app.add_typer(ingest_app, name="ingest")
app.command(name="search")(search_command)
app.add_typer(catalog_app, name="catalog")
app.command(name="remove")(remove_command)
app.command(name="discover")(discover_cmd)
app.command(name="download")(download_cmd)
app.command(name="doctor")(doctor_command)
app.command(name="export-bibtex")(export_bibtex_command)
app.command(name="related")(related_cmd)

from papermind.cli.audit import audit_app  # noqa: E402
from papermind.cli.backfill import backfill_cmd  # noqa: E402
from papermind.cli.context_pack import context_pack_cmd  # noqa: E402
from papermind.cli.crawl import crawl_cmd  # noqa: E402
from papermind.cli.equations import equations_app  # noqa: E402
from papermind.cli.migrate import migrate_cmd  # noqa: E402
from papermind.cli.tags import tags_app  # noqa: E402

app.add_typer(audit_app, name="audit")
app.add_typer(equations_app, name="equations")
app.command(name="backfill")(backfill_cmd)
app.command(name="context-pack")(context_pack_cmd)
app.command(name="crawl")(crawl_cmd)
app.command(name="migrate")(migrate_cmd)
app.add_typer(tags_app, name="tags")

from papermind.cli.brief import brief_cmd  # noqa: E402
from papermind.cli.chat import chat_cmd  # noqa: E402
from papermind.cli.pitfall import pitfall_add_cmd, pitfall_list_cmd  # noqa: E402
from papermind.cli.tables import tables_app  # noqa: E402
from papermind.cli.watch import watch_cmd  # noqa: E402

app.command(name="brief")(brief_cmd)
app.command(name="chat")(chat_cmd)
app.command(name="pitfall-add")(pitfall_add_cmd)
app.command(name="pitfall-list")(pitfall_list_cmd)
app.add_typer(tables_app, name="tables")
app.command(name="watch")(watch_cmd)


@app.command(name="reindex")
def reindex_command(ctx: typer.Context) -> None:
    """Rebuild catalog from filesystem and regenerate catalog.md."""
    kb_path = ctx.obj.get("kb") if ctx.obj else None
    if not kb_path or not (kb_path / ".papermind").exists():
        typer.echo("Error: --kb required and must point to initialized KB", err=True)
        raise typer.Exit(code=1)

    from papermind.catalog.index import CatalogIndex
    from papermind.catalog.render import render_catalog_md

    # Rebuild catalog.json from frontmatter (filesystem is truth)
    catalog = CatalogIndex.rebuild(kb_path)

    # Regenerate catalog.md
    (kb_path / "catalog.md").write_text(render_catalog_md(catalog.entries))

    # Trigger qmd reindex if available (best-effort)
    from papermind.query.qmd import qmd_reindex

    qmd_reindex(kb_path)

    console.print(f"Reindexed: {len(catalog.entries)} entries")


@app.command(name="serve")
def serve_command(
    ctx: typer.Context,
) -> None:
    """Start the MCP server (stdio transport)."""
    import asyncio

    from mcp.server.stdio import stdio_server

    from papermind.mcp_server import create_server

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
    target: int = typer.Option(
        0,
        "--target",
        help="Target number of ingested papers. Keeps fetching until reached.",
    ),
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

    Use ``--target N`` to keep fetching until N papers are ingested.
    The discovery limit auto-scales to find enough candidates.
    """

    kb_path = ctx.obj.get("kb") if ctx.obj else None
    offline = ctx.obj.get("offline", False)

    if not kb_path or not (kb_path / ".papermind").exists():
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
        from papermind.config import load_config

        config = load_config(kb_path)

        if target > 0:
            _fetch_until_target(
                ctx, query, target, topic, source, no_ingest, kb_path, config
            )
        else:
            _fetch_single_pass(
                ctx, query, limit, topic, source, no_ingest, dry_run, kb_path, config
            )

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


def _fetch_single_pass(
    ctx: typer.Context,
    query: str,
    limit: int,
    topic: str,
    source: str,
    no_ingest: bool,
    dry_run: bool,
    kb_path: Path,
    config: PaperMindConfig,
) -> None:
    """Single-pass fetch: discover → download → ingest."""
    import asyncio

    from papermind.discovery.orchestrator import discover_papers
    from papermind.discovery.providers import build_providers

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

    if dry_run:
        _print_dry_run_table(results)
        raise typer.Exit(code=0)

    downloaded = _download_results(results, kb_path)
    if not downloaded:
        console.print("[yellow]No papers downloaded.[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"\nDownloaded {len(downloaded)} paper(s)")

    if no_ingest:
        console.print("Skipping ingestion (--no-ingest)")
        raise typer.Exit(code=0)

    ingested = _ingest_downloaded(downloaded, topic, kb_path, config)
    console.print(f"\n[bold]{ingested} paper(s) ingested into topic '{topic}'[/bold]")


def _fetch_until_target(
    ctx: typer.Context,
    query: str,
    target: int,
    topic: str,
    source: str,
    no_ingest: bool,
    kb_path: Path,
    config: PaperMindConfig,
) -> None:
    """Keep fetching in batches until target papers are ingested."""
    import asyncio

    from papermind.discovery.orchestrator import discover_papers
    from papermind.discovery.providers import build_providers

    providers = build_providers(source, config)
    if not providers:
        console.print("[red]No providers available.[/red] Set API keys first.")
        raise typer.Exit(code=1)

    # Pre-seed seen DOIs/titles from catalog to skip known papers
    from papermind.catalog.index import CatalogIndex

    catalog = CatalogIndex(kb_path)
    existing = sum(1 for e in catalog.entries if e.topic == topic)
    seen_dois: set[str] = {e.doi.lower() for e in catalog.entries if e.doi}
    seen_titles: set[str] = {
        e.title.lower().strip() for e in catalog.entries if e.title
    }

    total_ingested = 0
    batch_limit = target * 4  # overshoot: ~25% yield expected
    max_discovery = target * 20  # safety cap
    max_rounds = 10  # hard stop regardless of discovery cap
    total_discovered = 0

    console.print(
        f"[bold]Target: {target} new paper(s)[/bold] for query: "
        f"[bold]{query}[/bold]\n"
        f"[dim]{existing} already in topic '{topic}' "
        f"(will be skipped)[/dim]"
    )

    round_num = 0
    while total_ingested < target:
        round_num += 1
        if round_num > max_rounds:
            console.print(
                f"[yellow]Reached max rounds ({max_rounds}). Stopping.[/yellow]"
            )
            break
        console.print(
            f"\n[dim]── Round {round_num}: discovering up to "
            f"{batch_limit} results ──[/dim]"
        )

        results = asyncio.run(discover_papers(query, providers, limit=batch_limit))

        if not results:
            console.print("[yellow]No more results from providers.[/yellow]")
            break

        # Filter out already-seen papers
        new_results = []
        for r in results:
            key_doi = r.doi.lower() if r.doi else ""
            key_title = r.title.lower().strip()
            if key_doi and key_doi in seen_dois:
                continue
            if key_title in seen_titles:
                continue
            if key_doi:
                seen_dois.add(key_doi)
            seen_titles.add(key_title)
            new_results.append(r)

        total_discovered += len(new_results)
        console.print(
            f"Found {len(new_results)} new result(s) "
            f"({total_discovered} total discovered)"
        )

        if not new_results:
            console.print("[yellow]No new results — providers exhausted.[/yellow]")
            break

        # Download
        downloaded = _download_results(new_results, kb_path)
        if downloaded and not no_ingest:
            # Trim batch to not overshoot
            still_need = target - total_ingested
            if len(downloaded) > still_need:
                downloaded = downloaded[:still_need]
            ingested = _ingest_downloaded(downloaded, topic, kb_path, config)
            total_ingested += ingested
            console.print(f"[bold]{total_ingested}/{target}[/bold] new papers ingested")

            # All downloads were duplicates — no point continuing
            if ingested == 0:
                console.print(
                    "[yellow]All papers already in KB (duplicates). Stopping.[/yellow]"
                )
                break
        elif downloaded:
            total_ingested += len(downloaded)
            console.print(f"[bold]{total_ingested}/{target}[/bold] papers downloaded")

        # If we didn't get enough, increase batch for next round
        if total_ingested < target:
            batch_limit = min(batch_limit * 2, 100)
            if total_discovered >= max_discovery:
                console.print(
                    f"[yellow]Reached discovery cap "
                    f"({max_discovery} results). Stopping.[/yellow]"
                )
                break

    console.print(
        f"\n[bold]{total_ingested} new paper(s) ingested "
        f"into topic '{topic}'[/bold] "
        f"({existing + total_ingested} total in topic)"
    )


def _print_dry_run_table(results: list) -> None:
    """Print the dry-run results table."""
    from rich.table import Table

    from papermind.discovery.orchestrator import _score_result

    table = Table(
        title="Discovery Results (dry-run)",
        show_header=True,
        header_style="bold",
        expand=True,
    )
    table.add_column("#", style="dim", no_wrap=True)
    table.add_column("Title", style="cyan", ratio=3)
    table.add_column("Abstract", style="dim", ratio=2)
    table.add_column("Cites", justify="right", no_wrap=True)
    table.add_column("PDF", justify="center", no_wrap=True)
    table.add_column("Score", justify="right", no_wrap=True)
    for idx, r in enumerate(results, 1):
        pdf = "[green]yes[/green]" if r.pdf_url else "[red]no[/red]"
        raw_abstract = r.abstract or ""
        abstract = (
            (raw_abstract[:80] + "...") if len(raw_abstract) > 80 else raw_abstract
        )
        table.add_row(
            str(idx),
            r.title[:60] if r.title else "(no title)",
            abstract or "[dim]—[/dim]",
            str(r.citation_count) if r.citation_count else "—",
            pdf,
            str(_score_result(r)),
        )
    console.print(table)


def _download_results(results: list, kb_path: Path | None = None) -> list[tuple]:
    """Download papers with PDF URLs, return (path, result) pairs.

    Args:
        results: List of PaperResult objects.
        kb_path: Knowledge base root (pdfs saved to kb_path/pdfs).
    """
    import asyncio

    from papermind.discovery.downloader import download_paper

    pdf_dir = (kb_path / "pdfs") if kb_path else (Path.cwd() / "pdfs")
    pdf_dir.mkdir(exist_ok=True)
    downloaded: list[tuple] = []

    for r in results:
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

    return downloaded


def _ingest_downloaded(
    downloaded: list[tuple],
    topic: str,
    kb_path: Path,
    config: PaperMindConfig,
) -> int:
    """Ingest downloaded papers, return count of successfully ingested."""
    from papermind.ingestion.paper import ingest_paper

    ingested = 0
    for pdf_path, paper_result in downloaded:
        try:
            entry = ingest_paper(
                pdf_path,
                topic,
                kb_path,
                config,
                no_reindex=True,
                abstract=paper_result.abstract,
                cites=paper_result.cites or None,
                cited_by=paper_result.cited_by or None,
            )
            if entry:
                console.print(f"  [green]Ingested[/green] {entry.title[:60]}")
                ingested += 1
            else:
                console.print("  [dim]Skipped[/dim] (duplicate)")
        except Exception as exc:
            console.print(f"  [red]Failed[/red] {pdf_path.name}: {exc}")

    return ingested


@app.command()
def version() -> None:
    """Print version."""
    from papermind import __version__

    typer.echo(f"papermind {__version__}")
