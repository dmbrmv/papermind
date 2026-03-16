"""papermind crawl — follow citation DOIs to build a connected KB."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def crawl_cmd(
    ctx: typer.Context,
    paper_id: str = typer.Argument(..., help="Paper ID to start crawling from"),
    depth: int = typer.Option(
        1, "--depth", "-d", help="How many levels of references to follow"
    ),
    topic: str = typer.Option(
        "uncategorized", "--topic", "-t", help="Topic for ingested papers"
    ),
    target: int = typer.Option(10, "--target", "-n", help="Max new papers to ingest"),
    direction: str = typer.Option(
        "cites",
        "--direction",
        help="Follow 'cites' (references), 'cited_by' (citations), or 'both'",
    ),
) -> None:
    """Follow citation DOIs from a seed paper to build a connected KB.

    Reads the ``cites`` and/or ``cited_by`` DOI lists from the seed paper's
    frontmatter, resolves each DOI, downloads open-access PDFs, and ingests
    them.  Then follows THEIR citations to the specified depth.

    Run ``papermind backfill`` first if seed papers lack citation data.

    Examples::

        # Follow references 2 levels deep from a seed paper
        papermind crawl paper-swat-calibration-2023 --depth 2 --topic hydrology

        # Follow both directions, cap at 20 new papers
        papermind crawl paper-lstm-streamflow --depth 1 --direction both --target 20
    """

    from papermind.config import load_config

    kb = _resolve_kb(ctx)
    config = load_config(kb)

    # Find seed paper
    seed_fm = _find_paper(kb, paper_id)
    if seed_fm is None:
        console.print(f"[red]Paper not found:[/red] {paper_id!r}")
        raise typer.Exit(code=1)

    seed_title = seed_fm.get("title", paper_id)
    seed_cites = seed_fm.get("cites", [])
    seed_cited_by = seed_fm.get("cited_by", [])

    # Collect DOIs to follow based on direction
    seed_dois = _collect_dois(seed_cites, seed_cited_by, direction)

    if not seed_dois:
        console.print(
            f"[yellow]No citation DOIs in[/yellow] {seed_title!r}\n"
            "[dim]Run `papermind backfill` to populate citation data.[/dim]"
        )
        raise typer.Exit(code=0)

    # Build set of DOIs already in KB
    known_dois = _known_dois_in_kb(kb)

    console.print(
        f"[bold]Crawling from:[/bold] {seed_title}\n"
        f"[dim]Depth: {depth}, direction: {direction}, "
        f"target: {target} new papers[/dim]\n"
        f"[dim]{len(seed_dois)} DOIs to follow, "
        f"{len(known_dois)} already in KB[/dim]"
    )

    total_ingested = 0
    current_dois = seed_dois

    for level in range(1, depth + 1):
        if total_ingested >= target:
            break

        # Filter to DOIs not already in KB
        new_dois = [d for d in current_dois if d.lower() not in known_dois]
        if not new_dois:
            console.print(f"\n[dim]── Depth {level}: no new DOIs to process ──[/dim]")
            break

        console.print(
            f"\n[dim]── Depth {level}: {len(new_dois)} new DOI(s) to resolve ──[/dim]"
        )

        # Resolve DOIs → download → ingest
        next_level_dois: list[str] = []
        remaining = target - total_ingested

        for doi in new_dois[: remaining * 3]:  # overshoot for yield
            if total_ingested >= target:
                break

            result = _resolve_and_ingest_doi(doi, topic, kb, config)
            if result is not None:
                entry, paper_cites, paper_cited_by = result
                total_ingested += 1
                known_dois.add(doi.lower())
                console.print(
                    f"  [green]OK[/green]   {entry.title[:60]} "
                    f"({len(paper_cites)} refs)"
                )

                # Collect DOIs for next depth level
                next_dois = _collect_dois(paper_cites, paper_cited_by, direction)
                next_level_dois.extend(next_dois)
            else:
                known_dois.add(doi.lower())  # don't retry

        console.print(f"[bold]{total_ingested}/{target}[/bold] papers ingested")
        current_dois = next_level_dois

    console.print(
        f"\n[bold]{total_ingested} new paper(s) ingested "
        f"into topic '{topic}'[/bold] via citation crawl"
    )


def _find_paper(kb: Path, paper_id: str) -> dict | None:
    """Find a paper's frontmatter by ID."""
    import frontmatter as fm_lib

    for md_file in kb.rglob("*.md"):
        if (
            md_file.name.startswith(".")
            or ".papermind" in md_file.parts
            or md_file.name == "catalog.md"
        ):
            continue
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("id") == paper_id:
                return dict(post.metadata)
        except Exception:
            continue
    return None


def _collect_dois(
    cites: list[str],
    cited_by: list[str],
    direction: str,
) -> list[str]:
    """Collect DOIs based on direction setting."""
    if direction == "cites":
        return list(cites)
    if direction == "cited_by":
        return list(cited_by)
    if direction == "both":
        return list(cites) + list(cited_by)
    return list(cites)


def _known_dois_in_kb(kb: Path) -> set[str]:
    """Build set of lowercase DOIs already in the KB."""
    import frontmatter as fm_lib

    dois: set[str] = set()
    for md_file in kb.rglob("*.md"):
        if (
            md_file.name.startswith(".")
            or ".papermind" in md_file.parts
            or md_file.name == "catalog.md"
        ):
            continue
        try:
            post = fm_lib.load(md_file)
            doi = post.metadata.get("doi", "")
            if doi:
                dois.add(doi.lower())
        except Exception:
            continue
    return dois


def _resolve_and_ingest_doi(
    doi: str,
    topic: str,
    kb: Path,
    config: object,
) -> tuple | None:
    """Resolve a DOI, download the PDF, and ingest it.

    Returns (CatalogEntry, cites, cited_by) on success, None on failure.
    """
    from papermind.discovery.downloader import download_paper
    from papermind.discovery.semantic_scholar import lookup_citations_by_doi
    from papermind.discovery.unpaywall import resolve_pdf_url
    from papermind.ingestion.paper import ingest_paper

    # Try to get PDF URL via Unpaywall
    pdf_url = asyncio.run(resolve_pdf_url(doi))
    if not pdf_url:
        console.print(f"  [dim]SKIP[/dim] {doi} — no PDF URL")
        return None

    # Download
    from papermind.discovery.base import PaperResult

    result = PaperResult(title=doi, doi=doi, pdf_url=pdf_url)
    pdf_dir = kb / "pdfs"
    pdf_dir.mkdir(exist_ok=True)

    pdf_path = asyncio.run(download_paper(result, pdf_dir))
    if not pdf_path:
        console.print(f"  [dim]FAIL[/dim] {doi} — download failed")
        return None

    # Get citation data from SS
    cites, cited_by = asyncio.run(lookup_citations_by_doi(doi))

    # Ingest
    try:
        entry = ingest_paper(
            pdf_path,
            topic,
            kb,
            config,
            no_reindex=True,
            cites=cites or None,
            cited_by=cited_by or None,
        )
        if entry is None:
            console.print(f"  [dim]SKIP[/dim] {doi} — duplicate")
            return None
        return entry, cites, cited_by
    except Exception as exc:
        console.print(f"  [red]FAIL[/red] {doi} — {exc}")
        return None
