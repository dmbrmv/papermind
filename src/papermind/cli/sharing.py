"""papermind export/import CLI — portable KB sharing."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def export_cmd(
    ctx: typer.Context,
    output: Path = typer.Option(..., "--output", "-o", help="Output .pmkb file path."),
    topic: str = typer.Option("", "--topic", "-t", help="Export only this topic."),
    entry_type: str = typer.Option(
        "", "--type", help="Export only this type (paper/package/codebase)."
    ),
) -> None:
    """Export KB entries to a portable .pmkb archive.

    Creates a zip archive containing papers with their markdown,
    originals, and metadata. Share with colleagues or back up your KB.

    Examples::

        papermind export -o hydrology.pmkb --topic hydrology
        papermind export -o full-backup.pmkb
    """
    from papermind.sharing import export_kb

    kb_path = _resolve_kb(ctx)
    stats = export_kb(kb_path, output, topic=topic, entry_type=entry_type)

    if stats["entries"] == 0:
        console.print("[yellow]No entries to export.[/yellow]")
        raise typer.Exit(code=0)

    size_mb = stats["bytes"] / (1024 * 1024)
    console.print(
        f"[green]Exported[/green] {stats['entries']} entries "
        f"({stats['files']} files, {size_mb:.1f} MB) to {output}"
    )


def import_cmd(
    ctx: typer.Context,
    archive: Path = typer.Argument(..., help="Path to .pmkb archive."),
    no_merge: bool = typer.Option(
        False, "--no-merge", help="Overwrite existing entries instead of skipping."
    ),
) -> None:
    """Import a .pmkb archive into the knowledge base.

    By default, entries with duplicate DOIs or titles are skipped.
    Use ``--no-merge`` to overwrite existing entries.

    Examples::

        papermind import hydrology.pmkb
        papermind import colleague-kb.pmkb --no-merge
    """
    from papermind.sharing import import_kb

    kb_path = _resolve_kb(ctx)
    resolved = archive.resolve()

    if not resolved.exists():
        console.print(f"[red]File not found:[/red] {resolved}")
        raise typer.Exit(code=1)

    stats = import_kb(kb_path, resolved, merge=not no_merge)

    console.print(
        f"[green]Imported[/green] {stats['imported']} entries "
        f"({stats['files']} files), "
        f"[yellow]{stats['skipped']}[/yellow] skipped (duplicates)"
    )
