"""papermind resolve/validate-refs CLI — agent memory integration."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def resolve_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Markdown file with kb: references."),
) -> None:
    """Resolve kb: references in a markdown file.

    Finds all ``kb:paper-id`` and ``kb:doi:10.xxx`` references and
    resolves them against the knowledge base, showing title and path.

    Examples::

        papermind resolve MEMORY.md
        papermind resolve docs/notes.md
    """
    from papermind.memory import (
        extract_kb_refs_from_file,
        format_resolved_refs,
        resolve_refs,
    )

    kb_path = _resolve_kb(ctx)
    resolved_path = path.resolve()

    if not resolved_path.is_file():
        console.print(f"[red]Not a file:[/red] {resolved_path}")
        raise typer.Exit(code=1)

    refs = extract_kb_refs_from_file(resolved_path)
    if not refs:
        console.print("No kb: references found in file.")
        raise typer.Exit(code=0)

    resolved = resolve_refs(refs, kb_path)
    console.print(format_resolved_refs(resolved))


def validate_refs_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Markdown file to validate."),
) -> None:
    """Validate that all kb: references in a file exist in the KB.

    Reports broken references that need to be updated or removed.

    Examples::

        papermind validate-refs MEMORY.md
    """
    from papermind.memory import format_validation, validate_refs_in_file

    kb_path = _resolve_kb(ctx)
    resolved_path = path.resolve()

    if not resolved_path.is_file():
        console.print(f"[red]Not a file:[/red] {resolved_path}")
        raise typer.Exit(code=1)

    valid, broken = validate_refs_in_file(resolved_path, kb_path)
    console.print(format_validation(valid, broken))

    if broken:
        raise typer.Exit(code=1)
