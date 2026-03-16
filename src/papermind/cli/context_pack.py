"""papermind context-pack — generate compressed briefing for agent context."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def context_pack_cmd(
    ctx: typer.Context,
    topic: str = typer.Argument(..., help="Topic to generate briefing for"),
    max_tokens: int = typer.Option(
        2000,
        "--max-tokens",
        "-n",
        help="Approximate max output tokens",
    ),
    output: str = typer.Option(
        "",
        "--output",
        "-o",
        help="Write to file instead of stdout",
    ),
) -> None:
    """Generate a compressed topic briefing for agent context injection.

    Produces a dense, structured block with the most relevant papers
    for a topic — pre-deduplicated, cross-referenced, with abstracts
    and citation counts. Designed for CLAUDE.md or session preambles.

    Examples::

        papermind context-pack hydrology --max-tokens 1500
        papermind context-pack ml-methods -n 3000 -o briefing.md
    """
    import frontmatter as fm_lib

    from papermind.catalog.index import CatalogIndex

    kb = _resolve_kb(ctx)
    catalog = CatalogIndex(kb)

    # Filter entries by topic
    entries = [e for e in catalog.entries if e.topic == topic]
    if not entries:
        console.print(f"[yellow]No entries in topic[/yellow] {topic!r}")
        raise typer.Exit(code=0)

    # Read frontmatter for each entry
    papers: list[dict] = []
    for entry in entries:
        md_path = kb / entry.path
        if not md_path.exists():
            continue
        try:
            post = fm_lib.load(md_path)
            meta = dict(post.metadata)
            meta["_path"] = entry.path
            papers.append(meta)
        except Exception:
            continue

    if not papers:
        console.print("[yellow]No readable papers.[/yellow]")
        raise typer.Exit(code=0)

    # Sort by citation count (richest metadata first)
    papers.sort(
        key=lambda p: len(p.get("cites", [])) + len(p.get("cited_by", [])),
        reverse=True,
    )

    # Build the briefing
    max_chars = max_tokens * 4  # rough token→char conversion
    lines = [
        f"# PaperMind Briefing: {topic}",
        f"> {len(papers)} papers in KB",
        "",
    ]
    total_chars = sum(len(line) for line in lines)

    for i, p in enumerate(papers, 1):
        title = p.get("title", "Untitled")
        doi = p.get("doi", "")
        year = p.get("year", "")
        abstract = p.get("abstract", "")
        tags = p.get("tags", [])
        cites = p.get("cites", [])
        cited_by = p.get("cited_by", [])

        block_lines = [f"## {i}. {title}"]
        meta_parts = []
        if year:
            meta_parts.append(str(year))
        if doi:
            meta_parts.append(f"DOI: {doi}")
        if cites or cited_by:
            meta_parts.append(f"{len(cites)} refs, {len(cited_by)} citations")
        if meta_parts:
            block_lines.append(" | ".join(meta_parts))

        if tags:
            block_lines.append(f"Tags: {', '.join(tags[:5])}")

        if abstract:
            # Truncate abstract to fit budget
            max_abstract = min(200, (max_chars - total_chars) // 3)
            if max_abstract > 50:
                trunc = (
                    abstract[:max_abstract] + "..."
                    if len(abstract) > max_abstract
                    else abstract
                )
                block_lines.append(f"\n{trunc}")

        block_lines.append(f"\nPath: {p.get('_path', '')}")
        block_lines.append("")

        block = "\n".join(block_lines)
        if total_chars + len(block) > max_chars:
            lines.append(
                f"\n*...{len(papers) - i + 1} more papers truncated "
                f"(budget: {max_tokens} tokens)*"
            )
            break
        lines.append(block)
        total_chars += len(block)

    result = "\n".join(lines)

    if output:
        Path(output).write_text(result)
        console.print(f"[green]Written to[/green] {output}")
    else:
        typer.echo(result)
