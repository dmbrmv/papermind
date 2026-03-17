"""papermind pitfall — manage anti-pattern warnings on papers."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from papermind.cli.utils import _resolve_kb

console = Console()


def pitfall_add_cmd(
    ctx: typer.Context,
    paper_id: str = typer.Argument(..., help="Paper ID"),
    pattern: str = typer.Option(
        ..., "--pattern", "-p", help="Code pattern to match (regex or substring)"
    ),
    warning: str = typer.Option(
        ..., "--warning", "-w", help="Warning message to surface"
    ),
) -> None:
    """Add an anti-pattern warning to a paper.

    When ``papermind watch`` scans a code file and the file content
    matches the pattern, the warning is surfaced alongside the
    search results.

    Examples::

        papermind pitfall-add paper-swat-calibration \\
            -p "CN.*retention.*parameter" \\
            -w "SWAT+ CN has two code paths (daily vs sub-daily)"

        papermind pitfall-add paper-lstm-streamflow \\
            -p "teacher_forcing" \\
            -w "Teacher forcing during eval causes data leakage"
    """
    import frontmatter as fm_lib

    kb = _resolve_kb(ctx)
    for md_file in kb.rglob("*.md"):
        if (
            md_file.name.startswith(".")
            or ".papermind" in md_file.parts
            or md_file.name == "catalog.md"
        ):
            continue
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("id") != paper_id:
                continue

            pitfalls = post.metadata.get("pitfalls", [])
            pitfalls.append({"pattern": pattern, "warning": warning})
            post.metadata["pitfalls"] = pitfalls
            md_file.write_text(fm_lib.dumps(post))

            console.print(
                f"[green]Added pitfall[/green] to {paper_id}\n"
                f"  Pattern: {pattern}\n"
                f"  Warning: {warning}"
            )
            return
        except Exception:
            continue

    console.print(f"[red]Paper not found:[/red] {paper_id!r}")
    raise typer.Exit(code=1)


def pitfall_list_cmd(
    ctx: typer.Context,
) -> None:
    """List all anti-pattern warnings across the KB."""
    import frontmatter as fm_lib

    kb = _resolve_kb(ctx)
    papers_dir = kb / "papers"
    if not papers_dir.exists():
        console.print("[dim]No papers.[/dim]")
        raise typer.Exit(code=0)

    table = Table(
        title="Anti-Pattern Warnings",
        show_header=True,
    )
    table.add_column("Paper", style="cyan", ratio=2)
    table.add_column("Pattern", ratio=2)
    table.add_column("Warning", ratio=3)

    count = 0
    for md_file in sorted(papers_dir.rglob("*.md")):
        if md_file.name == "catalog.md":
            continue
        try:
            post = fm_lib.load(md_file)
            pitfalls = post.metadata.get("pitfalls", [])
            pid = post.metadata.get("id", "")
            for pf in pitfalls:
                table.add_row(
                    pid[:30],
                    pf.get("pattern", "")[:30],
                    pf.get("warning", "")[:50],
                )
                count += 1
        except Exception:
            continue

    if count == 0:
        console.print(
            "[dim]No pitfalls defined. Use `papermind pitfall-add` to add one.[/dim]"
        )
        raise typer.Exit(code=0)

    console.print(table)
    console.print(f"[dim]{count} pitfall(s)[/dim]")
