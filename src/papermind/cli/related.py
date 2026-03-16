"""papermind related CLI command — show citation-linked papers in the KB."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from papermind.cli.utils import _resolve_kb

console = Console()


def related_cmd(
    ctx: typer.Context,
    paper_id: str = typer.Argument(
        ..., help="Paper ID (e.g. paper-swat-calibration-2023)"
    ),
) -> None:
    """Show papers in the knowledge base connected by citations.

    Reads the frontmatter ``cites`` and ``cited_by`` fields to find papers
    that reference or are referenced by the given paper.  Only papers already
    in the KB are shown.
    """

    kb = _resolve_kb(ctx)
    target_fm = _find_paper_frontmatter(kb, paper_id)

    if target_fm is None:
        console.print(f"[red]Paper not found:[/red] {paper_id!r}")
        raise typer.Exit(code=1)

    target_title = target_fm.get("title", paper_id)
    target_doi = target_fm.get("doi", "")
    cites_dois = set(target_fm.get("cites", []))
    cited_by_dois = set(target_fm.get("cited_by", []))

    if not cites_dois and not cited_by_dois:
        console.print(
            f"[yellow]No citation data for[/yellow] {target_title!r}\n"
            "[dim]Citation data comes from Semantic Scholar during discovery.[/dim]"
        )
        raise typer.Exit(code=0)

    # Build DOI → (id, title) index from all papers in the KB
    doi_index = _build_doi_index(kb)

    # Find matches
    refs_in_kb = [(doi, *doi_index[doi]) for doi in cites_dois if doi in doi_index]
    citers_in_kb = [(doi, *doi_index[doi]) for doi in cited_by_dois if doi in doi_index]

    # Also check: which other papers in the KB cite or are cited by this one?
    reverse_refs, reverse_citers = _find_reverse_links(kb, target_doi)
    # Merge reverse links (deduplicate by DOI)
    seen_citer_dois = {doi for doi, _, _ in citers_in_kb}
    for doi, pid, title in reverse_citers:
        if doi not in seen_citer_dois:
            citers_in_kb.append((doi, pid, title))
            seen_citer_dois.add(doi)

    seen_ref_dois = {doi for doi, _, _ in refs_in_kb}
    for doi, pid, title in reverse_refs:
        if doi not in seen_ref_dois:
            refs_in_kb.append((doi, pid, title))
            seen_ref_dois.add(doi)

    console.print(f"\n[bold]Related papers for:[/bold] {target_title}")
    if target_doi:
        console.print(f"[dim]DOI: {target_doi}[/dim]")

    if refs_in_kb:
        table = Table(title="References (this paper cites)", show_header=True)
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        table.add_column("DOI", style="dim")
        for doi, pid, title in refs_in_kb:
            table.add_row(pid, title[:60], doi)
        console.print(table)
    else:
        console.print(
            f"[dim]References: {len(cites_dois)} DOI(s) in metadata, "
            "0 found in KB[/dim]"
        )

    if citers_in_kb:
        table = Table(title="Cited by (papers that cite this one)", show_header=True)
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        table.add_column("DOI", style="dim")
        for doi, pid, title in citers_in_kb:
            table.add_row(pid, title[:60], doi)
        console.print(table)
    else:
        console.print(
            f"[dim]Cited by: {len(cited_by_dois)} DOI(s) in metadata, "
            "0 found in KB[/dim]"
        )

    total = len(refs_in_kb) + len(citers_in_kb)
    console.print(f"\n[bold]{total}[/bold] related paper(s) in KB")


def _find_paper_frontmatter(kb: Path, paper_id: str) -> dict | None:
    """Find a paper's frontmatter by ID.

    Args:
        kb: Knowledge base root.
        paper_id: Paper ID to look up.

    Returns:
        Frontmatter dict if found, None otherwise.
    """
    import frontmatter as fm_lib

    for md_file in kb.rglob("*.md"):
        if md_file.name.startswith(".") or ".papermind" in md_file.parts:
            continue
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("id") == paper_id:
                return dict(post.metadata)
        except Exception:
            continue
    return None


def _build_doi_index(kb: Path) -> dict[str, tuple[str, str]]:
    """Build a DOI → (paper_id, title) index from all papers in the KB.

    Args:
        kb: Knowledge base root.

    Returns:
        Dict mapping DOI strings to (id, title) tuples.
    """
    import frontmatter as fm_lib

    index: dict[str, tuple[str, str]] = {}
    for md_file in kb.rglob("*.md"):
        if md_file.name.startswith(".") or ".papermind" in md_file.parts:
            continue
        try:
            post = fm_lib.load(md_file)
            meta = post.metadata
            doi = meta.get("doi", "")
            if doi and meta.get("type") == "paper":
                index[doi] = (meta.get("id", ""), meta.get("title", ""))
        except Exception:
            continue
    return index


def _find_reverse_links(
    kb: Path, target_doi: str
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Find papers whose cites/cited_by lists mention the target DOI.

    Args:
        kb: Knowledge base root.
        target_doi: DOI of the paper we're searching for links to.

    Returns:
        Tuple of (papers that cite target, papers that target cites).
        Each item is (doi, paper_id, title).
    """
    import frontmatter as fm_lib

    if not target_doi:
        return [], []

    refs: list[tuple[str, str, str]] = []
    citers: list[tuple[str, str, str]] = []

    for md_file in kb.rglob("*.md"):
        if md_file.name.startswith(".") or ".papermind" in md_file.parts:
            continue
        try:
            post = fm_lib.load(md_file)
            meta = post.metadata
            if meta.get("type") != "paper":
                continue
            doi = meta.get("doi", "")
            pid = meta.get("id", "")
            title = meta.get("title", "")

            # If this paper's cites list includes target_doi,
            # then this paper cites the target → it's a "cited_by" for target
            if target_doi in (meta.get("cites") or []):
                citers.append((doi, pid, title))

            # If this paper's cited_by list includes target_doi,
            # then target cites this paper → it's a "reference" for target
            if target_doi in (meta.get("cited_by") or []):
                refs.append((doi, pid, title))
        except Exception:
            continue

    return refs, citers
