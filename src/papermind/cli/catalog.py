"""papermind catalog CLI — show, stats commands and remove top-level command."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from papermind.cli.utils import _resolve_kb

catalog_app = typer.Typer(
    name="catalog",
    help="Inspect the knowledge base catalog.",
    no_args_is_help=True,
)

console = Console()


@catalog_app.command(name="show")
def catalog_show(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Print raw catalog.json."),
    topic: str = typer.Option("", "--topic", "-t", help="Filter entries by topic."),
) -> None:
    """Print catalog contents to the terminal."""
    import json

    from papermind.catalog.index import CatalogIndex
    from papermind.catalog.render import render_catalog_md

    kb_path = _resolve_kb(ctx)
    index = CatalogIndex(kb_path)

    entries = index.entries
    if topic:
        entries = [e for e in entries if e.topic == topic]
        if not entries:
            console.print(
                f"[yellow]No entries with topic[/yellow] [bold]{topic!r}[/bold]"
            )
            raise typer.Exit(code=0)

    if json_output:
        data = [e.to_dict() for e in entries]
        typer.echo(json.dumps(data, indent=2))
        return

    typer.echo(render_catalog_md(entries))


@catalog_app.command(name="stats")
def catalog_stats(ctx: typer.Context) -> None:
    """Print a summary table of the knowledge base contents."""
    from papermind.catalog.index import CatalogIndex

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
    from papermind.catalog.index import CatalogIndex
    from papermind.catalog.render import render_catalog_md

    kb_path = _resolve_kb(ctx)
    index = CatalogIndex(kb_path)

    entry = index.get(entry_id)
    if entry is None:
        console.print(f"[red]Entry not found:[/red] {entry_id}")
        raise typer.Exit(code=1)

    # Collect all files to delete (with path traversal protection)
    to_delete: list[Path] = []
    for rel_path in [entry.path, *entry.files]:
        target = (kb_path / rel_path).resolve()
        if not target.is_relative_to(kb_path.resolve()):
            console.print(f"[red]Path traversal blocked:[/red] {rel_path}")
            raise typer.Exit(code=1)
        to_delete.append(target)

    # Delete files
    for target in to_delete:
        if target.exists():
            target.unlink()

    # Clean empty parent directories
    dirs_seen: set[Path] = set()
    for target in to_delete:
        dirs_seen.add(target.parent)
    for d in dirs_seen:
        try:
            if d.exists() and d != kb_path.resolve() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass

    # Remove from catalog index and regenerate catalog.md
    index.remove(entry_id)
    (kb_path / "catalog.md").write_text(render_catalog_md(index.entries))

    console.print(f"[green]Removed[/green] entry [bold]{entry_id}[/bold]")


def export_bibtex_command(ctx: typer.Context) -> None:
    """Export catalog papers with DOIs to BibTeX format."""
    from papermind.catalog.index import CatalogIndex

    kb_path = _resolve_kb(ctx)
    index = CatalogIndex(kb_path)

    bibtex_entries = []
    for entry in index.entries:
        if entry.type != "paper" or not entry.doi:
            continue
        # Extract year from entry.added (first 4 chars) if not stored explicitly
        year = entry.added[:4] if entry.added and len(entry.added) >= 4 else ""
        title = (
            entry.title.replace("{", "\\{").replace("}", "\\}") if entry.title else ""
        )
        bibtex_entries.append(
            f"@article{{{entry.id},\n"
            f"  title = {{{title}}},\n"
            f"  doi = {{{entry.doi}}},\n"
            f"  year = {{{year}}},\n"
            f"}}"
        )

    if not bibtex_entries:
        console.print("[yellow]No papers with DOIs found in catalog.[/yellow]")
        raise typer.Exit(code=0)

    typer.echo("\n\n".join(bibtex_entries))
