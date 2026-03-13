"""hydrofound catalog CLI — show, stats commands and remove top-level command."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

catalog_app = typer.Typer(
    name="catalog",
    help="Inspect the knowledge base catalog.",
    no_args_is_help=True,
)

console = Console()


def _resolve_kb(ctx: typer.Context) -> Path:
    """Resolve the KB path from context or raise an error."""
    kb: Path | None = ctx.obj.get("kb") if ctx.obj else None
    if kb is None:
        console.print(
            "[red]No knowledge base specified.[/red] "
            "Pass --kb <path> or run from within a KB directory."
        )
        raise typer.Exit(code=1)
    if not (kb / ".hydrofound").exists():
        console.print(
            f"[red]Not a valid HydroFound KB:[/red] {kb}\n"
            "Run [bold]hydrofound init[/bold] to create one."
        )
        raise typer.Exit(code=1)
    return kb


@catalog_app.command(name="show")
def catalog_show(ctx: typer.Context) -> None:
    """Print catalog.md content to the terminal."""
    kb_path = _resolve_kb(ctx)
    catalog_md = kb_path / "catalog.md"
    if not catalog_md.exists():
        console.print("[yellow]catalog.md not found.[/yellow]")
        raise typer.Exit(code=1)
    typer.echo(catalog_md.read_text())


@catalog_app.command(name="stats")
def catalog_stats(ctx: typer.Context) -> None:
    """Print a summary table of the knowledge base contents."""
    from hydrofound.catalog.index import CatalogIndex

    kb_path = _resolve_kb(ctx)
    index = CatalogIndex(kb_path)
    stats = index.stats()

    table = Table(title="Knowledge Base Stats", show_header=True, header_style="bold")
    table.add_column("Type", style="cyan")
    table.add_column("Count", justify="right")

    table.add_row("Papers", str(stats["papers"]))
    table.add_row("Packages", str(stats["packages"]))
    table.add_row("Codebases", str(stats["codebases"]))

    console.print(table)

    topics: dict[str, int] = stats.get("topics", {})
    if topics:
        topic_table = Table(title="Topics", show_header=True, header_style="bold")
        topic_table.add_column("Topic", style="cyan")
        topic_table.add_column("Entries", justify="right")
        for topic, count in sorted(topics.items()):
            topic_table.add_row(topic, str(count))
        console.print(topic_table)


def remove_command(
    ctx: typer.Context,
    entry_id: str = typer.Argument(..., help="ID of the catalog entry to remove."),
) -> None:
    """Delete an entry's files and remove it from the catalog."""
    from hydrofound.catalog.index import CatalogIndex
    from hydrofound.catalog.render import render_catalog_md

    kb_path = _resolve_kb(ctx)
    index = CatalogIndex(kb_path)

    entry = index.get(entry_id)
    if entry is None:
        console.print(f"[red]Entry not found:[/red] {entry_id}")
        raise typer.Exit(code=1)

    # Delete the primary file
    primary_file = kb_path / entry.path
    if primary_file.exists():
        primary_file.unlink()

    # Delete any additional files listed on the entry
    for rel_path in entry.files:
        extra_file = kb_path / rel_path
        if extra_file.exists():
            extra_file.unlink()

    # Remove from catalog index and regenerate catalog.md
    index.remove(entry_id)
    (kb_path / "catalog.md").write_text(render_catalog_md(index.entries))

    console.print(f"[green]Removed[/green] entry [bold]{entry_id}[/bold]")
