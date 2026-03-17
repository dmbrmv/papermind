"""papermind backfill — enrich existing papers with citation data."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def backfill_cmd(ctx: typer.Context) -> None:
    """Backfill citation data for papers that have DOIs but no cites/cited_by.

    Queries Semantic Scholar's single-paper endpoint for each paper with a
    DOI, retrieves reference and citation DOI lists, and writes them to
    the paper's frontmatter.  Papers without DOIs or already having
    citation data are skipped.
    """
    import frontmatter as fm_lib

    kb = _resolve_kb(ctx)
    papers_dir = kb / "papers"
    if not papers_dir.exists():
        console.print("[yellow]No papers/ directory found.[/yellow]")
        raise typer.Exit(code=0)

    # Collect papers needing backfill
    candidates: list[tuple] = []  # (md_path, doi)
    for md_file in sorted(papers_dir.rglob("paper.md")):
        try:
            post = fm_lib.load(md_file)
            doi = post.metadata.get("doi", "")
            cites = post.metadata.get("cites", [])
            cited_by = post.metadata.get("cited_by", [])
            if doi and not cites and not cited_by:
                candidates.append((md_file, doi))
        except Exception:
            continue

    # Also check legacy flat layout (slug.md, not paper.md)
    for md_file in sorted(papers_dir.rglob("*.md")):
        if md_file.name == "paper.md" or md_file.name == "catalog.md":
            continue
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("type") != "paper":
                continue
            doi = post.metadata.get("doi", "")
            cites = post.metadata.get("cites", [])
            cited_by = post.metadata.get("cited_by", [])
            if doi and not cites and not cited_by:
                # Avoid duplicates if already found as paper.md
                if not any(c[1] == doi for c in candidates):
                    candidates.append((md_file, doi))
        except Exception:
            continue

    if not candidates:
        console.print(
            "[dim]No papers need backfill (all have citation data or lack DOIs).[/dim]"
        )
        raise typer.Exit(code=0)

    console.print(f"[bold]{len(candidates)} paper(s) to backfill[/bold]")

    enriched = 0
    failed = 0

    for md_path, doi in candidates:
        cites, cited_by = asyncio.run(_lookup_one(doi))

        if not cites and not cited_by:
            console.print(f"  [dim]SKIP[/dim] {doi} — no data from SS")
            failed += 1
            continue

        # Update frontmatter
        post = fm_lib.load(md_path)
        if cites:
            post.metadata["cites"] = cites
        if cited_by:
            post.metadata["cited_by"] = cited_by
        md_path.write_text(fm_lib.dumps(post))

        console.print(
            f"  [green]OK[/green]   {doi} — "
            f"{len(cites)} refs, {len(cited_by)} citations"
        )
        enriched += 1

    console.print(f"\n[bold]{enriched} enriched[/bold], {failed} skipped (no data)")


async def _lookup_one(doi: str) -> tuple[list[str], list[str]]:
    """Look up citations for a single DOI via OpenAlex."""
    from papermind.discovery.openalex import lookup_citations_openalex

    return await lookup_citations_openalex(doi)
