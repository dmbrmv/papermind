"""papermind migrate — convert legacy flat layout to per-paper directories."""

from __future__ import annotations

import shutil

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def migrate_cmd(ctx: typer.Context) -> None:
    """Migrate papers from flat layout to per-paper subdirectories.

    Converts the legacy layout::

        papers/topic/slug.md + slug.pdf + slug/

    to the new per-paper layout::

        papers/topic/slug/paper.md + original.pdf + images/

    Idempotent — already-migrated papers are skipped.
    Rebuilds the catalog after migration.
    """
    kb = _resolve_kb(ctx)
    papers_dir = kb / "papers"
    if not papers_dir.exists():
        console.print("[yellow]No papers/ directory found.[/yellow]")
        raise typer.Exit(code=0)

    migrated = 0
    skipped = 0

    for topic_dir in sorted(papers_dir.iterdir()):
        if not topic_dir.is_dir():
            continue

        # Find flat .md files (not paper.md inside subdirs)
        for md_file in sorted(topic_dir.glob("*.md")):
            if md_file.name == "paper.md":
                # This is already the new layout (shouldn't happen at
                # topic level, but skip anyway)
                continue

            slug = md_file.stem
            paper_dir = topic_dir / slug

            # Check if already migrated (paper_dir/paper.md exists)
            if (paper_dir / "paper.md").exists():
                skipped += 1
                continue

            paper_dir.mkdir(exist_ok=True)

            # Move markdown → paper.md
            shutil.move(str(md_file), str(paper_dir / "paper.md"))

            # Move PDF → original.pdf
            pdf_file = topic_dir / f"{slug}.pdf"
            if pdf_file.exists():
                shutil.move(str(pdf_file), str(paper_dir / "original.pdf"))

            # Move existing image directory → images/
            # Old layout: topic/slug/ with figures inside
            # If paper_dir already existed as image dir, rename contents
            old_images = list(paper_dir.glob("figure_*"))
            if old_images:
                images_dir = paper_dir / "images"
                images_dir.mkdir(exist_ok=True)
                for img in old_images:
                    shutil.move(str(img), str(images_dir / img.name))

                # Update image references in paper.md
                paper_md = paper_dir / "paper.md"
                content = paper_md.read_text(encoding="utf-8")
                content = content.replace(f"{slug}/", "images/")
                paper_md.write_text(content, encoding="utf-8")

            migrated += 1
            console.print(f"  [green]Migrated[/green] {slug}")

    if migrated == 0 and skipped == 0:
        console.print("[dim]No papers to migrate.[/dim]")
        raise typer.Exit(code=0)

    # Rebuild catalog from filesystem
    from papermind.catalog.index import CatalogIndex
    from papermind.catalog.render import render_catalog_md

    catalog = CatalogIndex.rebuild(kb)
    (kb / "catalog.md").write_text(render_catalog_md(catalog.entries))

    from papermind.query.qmd import qmd_reindex

    qmd_reindex(kb)

    console.print(
        f"\n[bold]{migrated} paper(s) migrated[/bold]"
        f"{f', {skipped} already migrated' if skipped else ''}"
    )
