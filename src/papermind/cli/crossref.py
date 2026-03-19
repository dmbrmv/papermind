"""papermind crossref CLI — compute keyword-based cross-references."""

from __future__ import annotations

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def crossref_cmd(
    ctx: typer.Context,
    save: bool = typer.Option(
        False, "--save", help="Write keyword_related to paper frontmatter."
    ),
    min_score: float = typer.Option(
        0.15, "--min-score", help="Minimum Jaccard similarity threshold (0-1)."
    ),
) -> None:
    """Compute keyword-based cross-references between papers.

    Uses tag overlap (Jaccard similarity) to find related papers beyond
    the citation graph.  By default, prints results without modifying
    files.  Use ``--save`` to write ``keyword_related`` field to paper
    frontmatter.

    Examples::

        papermind crossref                  # preview
        papermind crossref --save           # write to frontmatter
        papermind crossref --min-score 0.2  # stricter threshold
    """
    from papermind.crossref import backfill_cross_refs, compute_cross_refs

    kb_path = _resolve_kb(ctx)

    cross_refs = compute_cross_refs(kb_path, min_score=min_score)

    if not cross_refs:
        console.print(
            "[yellow]No cross-references found.[/yellow] "
            "Papers need tags — run `papermind tags refresh` first."
        )
        raise typer.Exit(code=0)

    total_links = sum(len(v) for v in cross_refs.values())
    console.print(
        f"Found [bold]{total_links}[/bold] cross-reference link(s) "
        f"across [bold]{len(cross_refs)}[/bold] paper(s)\n"
    )

    # Print top connections
    for paper_id, related in sorted(
        cross_refs.items(), key=lambda x: -max(s for _, s in x[1])
    )[:15]:
        top_rel = related[0]
        console.print(
            f"  {paper_id} → {top_rel[0]} "
            f"[dim](score: {top_rel[1]:.2f}, +{len(related) - 1} more)[/dim]"
        )

    if len(cross_refs) > 15:
        console.print(f"  [dim]... and {len(cross_refs) - 15} more papers[/dim]")

    if save:
        updated = backfill_cross_refs(kb_path, min_score=min_score)
        console.print(
            f"\n[green]Updated[/green] {updated} paper(s) with keyword_related."
        )
    else:
        console.print("\n[dim]Use --save to write to frontmatter.[/dim]")
