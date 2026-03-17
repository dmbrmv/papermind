"""papermind tables — extract and display tables from papers."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from papermind.cli.utils import _resolve_kb

console = Console()

tables_app = typer.Typer(
    name="tables",
    help="Extract and display tables from papers.",
    no_args_is_help=True,
)


@tables_app.command(name="show")
def tables_show(
    ctx: typer.Context,
    paper_id: str = typer.Argument(..., help="Paper ID"),
) -> None:
    """Show tables extracted from a paper."""
    import frontmatter as fm_lib

    kb = _resolve_kb(ctx)
    for md_file in kb.rglob("*.md"):
        if md_file.name == "catalog.md" or ".papermind" in md_file.parts:
            continue
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("id") != paper_id:
                continue

            extracted = post.metadata.get("tables", [])
            if not extracted:
                console.print(
                    f"[yellow]No tables in[/yellow] {paper_id}\n"
                    "[dim]Run `papermind tables backfill` first.[/dim]"
                )
                return

            for idx, tbl in enumerate(extracted, 1):
                headers = tbl.get("headers", [])
                rows = tbl.get("rows", [])
                caption = tbl.get("caption", "")
                section = tbl.get("section", "")

                title = f"Table {idx}"
                if caption:
                    title += f": {caption[:60]}"
                if section:
                    title += f" ({section[:30]})"

                rt = Table(title=title, show_header=True)
                for h in headers:
                    rt.add_column(h[:20])
                for row in rows[:20]:  # cap display rows
                    rt.add_row(*[c[:25] for c in row])
                console.print(rt)
                if len(rows) > 20:
                    console.print(f"[dim]...{len(rows) - 20} more rows[/dim]")
                console.print()

            console.print(f"[dim]{len(extracted)} table(s) total[/dim]")
            return
        except Exception:
            continue

    console.print(f"[red]Paper not found:[/red] {paper_id!r}")
    raise typer.Exit(code=1)


@tables_app.command(name="backfill")
def tables_backfill(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show counts without writing"
    ),
) -> None:
    """Extract tables for all papers and store in frontmatter."""
    import frontmatter as fm_lib

    from papermind.ingestion.tables import extract_tables

    kb = _resolve_kb(ctx)
    papers_dir = kb / "papers"
    if not papers_dir.exists():
        console.print("[yellow]No papers/ directory.[/yellow]")
        raise typer.Exit(code=0)

    updated = 0
    for md_file in sorted(papers_dir.rglob("*.md")):
        if md_file.name == "catalog.md":
            continue
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("type") != "paper":
                continue

            pid = post.metadata.get("id", md_file.stem)
            tables = extract_tables(post.content)

            total_rows = sum(t.num_rows for t in tables)
            console.print(
                f"  {pid[:50]:50s} → {len(tables)} table(s), {total_rows} rows"
            )

            if not dry_run and tables:
                post.metadata["tables"] = [t.to_dict() for t in tables]
                post.metadata["table_count"] = len(tables)
                md_file.write_text(fm_lib.dumps(post))
                updated += 1
        except Exception:
            continue

    if dry_run:
        console.print("[dim]Dry run — no changes written.[/dim]")
    else:
        console.print(f"\n[bold]{updated} paper(s) updated[/bold]")
