"""papermind equations — extract and search equations from papers."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from papermind.cli.utils import _resolve_kb

console = Console()

equations_app = typer.Typer(
    name="equations",
    help="Extract and search equations from papers.",
    no_args_is_help=True,
)


@equations_app.command(name="show")
def equations_show(
    ctx: typer.Context,
    paper_id: str = typer.Argument(..., help="Paper ID"),
) -> None:
    """Show equations extracted from a paper."""
    import frontmatter as fm_lib

    kb = _resolve_kb(ctx)
    for md_file in kb.rglob("*.md"):
        if md_file.name == "catalog.md" or ".papermind" in md_file.parts:
            continue
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("id") != paper_id:
                continue

            equations = post.metadata.get("equations", [])
            if not equations:
                console.print(
                    f"[yellow]No equations in[/yellow] {paper_id}\n"
                    "[dim]Run `papermind equations backfill` to extract.[/dim]"
                )
                return

            table = Table(
                title=f"Equations: {paper_id}",
                show_header=True,
            )
            table.add_column("#", style="dim", no_wrap=True)
            table.add_column("LaTeX", ratio=4)
            table.add_column("Section", style="cyan", ratio=2)

            for eq in equations:
                if not eq.get("display", True):
                    continue  # skip inline for display
                table.add_row(
                    eq.get("number", "—"),
                    eq.get("latex", "")[:80],
                    eq.get("section", "")[:40],
                )
            console.print(table)
            console.print(
                f"[dim]{len(equations)} equation(s) total "
                f"({sum(1 for e in equations if e.get('display'))} display, "
                f"{sum(1 for e in equations if not e.get('display'))} inline)[/dim]"
            )
            return
        except Exception:
            continue

    console.print(f"[red]Paper not found:[/red] {paper_id!r}")
    raise typer.Exit(code=1)


@equations_app.command(name="backfill")
def equations_backfill(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show counts without writing"
    ),
) -> None:
    """Extract equations for all papers and store in frontmatter."""
    import frontmatter as fm_lib

    from papermind.ingestion.equations import extract_equations

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
            equations = extract_equations(post.content)

            console.print(f"  {pid[:50]:50s} → {len(equations)} equation(s)")

            if not dry_run and equations:
                post.metadata["equations"] = [eq.to_dict() for eq in equations]
                post.metadata["equation_count"] = len(equations)
                md_file.write_text(fm_lib.dumps(post))
                updated += 1
        except Exception:
            continue

    if dry_run:
        console.print("[dim]Dry run — no changes written.[/dim]")
    else:
        console.print(f"\n[bold]{updated} paper(s) updated[/bold]")
