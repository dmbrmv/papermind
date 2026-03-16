"""papermind tags — auto-tagging via TF-IDF keyword extraction."""

from __future__ import annotations

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()

tags_app = typer.Typer(
    name="tags",
    help="Auto-tagging for papers in the knowledge base.",
    no_args_is_help=True,
)


@tags_app.command(name="refresh")
def tags_refresh(
    ctx: typer.Context,
    max_tags: int = typer.Option(8, "--max-tags", "-n", help="Max tags per paper"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show tags without writing"),
) -> None:
    """Recompute tags for all papers using TF-IDF.

    Analyzes the full paper corpus and extracts distinctive keywords
    for each paper. Tags are written to the ``tags`` field in
    frontmatter.
    """

    from papermind.tagging import tag_all_papers

    kb = _resolve_kb(ctx)
    result = tag_all_papers(kb, max_tags=max_tags)

    if not result:
        console.print("[yellow]No papers to tag.[/yellow]")
        raise typer.Exit(code=0)

    updated = 0
    for paper_id, tags in sorted(result.items()):
        tag_str = ", ".join(tags)
        console.print(f"  {paper_id[:50]:50s} → {tag_str}")

        if not dry_run:
            _write_tags(kb, paper_id, tags)
            updated += 1

    if dry_run:
        console.print(
            f"\n[dim]{len(result)} paper(s) would be tagged "
            "(dry-run, no changes written)[/dim]"
        )
    else:
        # Rebuild catalog so tags appear in catalog.json
        from papermind.catalog.index import CatalogIndex
        from papermind.catalog.render import render_catalog_md

        catalog = CatalogIndex.rebuild(kb)
        (kb / "catalog.md").write_text(render_catalog_md(catalog.entries))
        console.print(f"\n[bold]{updated} paper(s) tagged[/bold]")


def _write_tags(kb, paper_id: str, tags: list[str]) -> None:
    """Write tags to a paper's frontmatter."""
    import frontmatter as fm_lib

    papers_dir = kb / "papers"
    for md_file in papers_dir.rglob("*.md"):
        if md_file.name == "catalog.md":
            continue
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("id") == paper_id:
                post.metadata["tags"] = tags
                md_file.write_text(fm_lib.dumps(post))
                return
        except Exception:
            continue
