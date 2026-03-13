"""hydrofound doctor — dependency health check."""

from __future__ import annotations

import os
import shutil

import typer
from rich.console import Console

console = Console()


def doctor_command(
    ctx: typer.Context,
) -> None:
    """Check HydroFound dependencies and configuration."""
    kb_path = ctx.obj.get("kb") if ctx.obj else None

    console.print("\n[bold]HydroFound Doctor[/bold]")
    console.print("═" * 40)

    # Check dependencies
    console.print("\n[bold]Dependencies:[/bold]")
    deps = [
        ("griffe", "griffe", "Python API extraction"),
        ("marker", "marker", "PDF conversion — pip install marker-pdf"),
        ("qmd", "qmd", "Semantic search — github.com/tobi/qmd"),
        ("node", "node", "Required by qmd (node >= 22)"),
    ]

    for name, cmd, desc in deps:
        found = shutil.which(cmd) is not None
        icon = "[green]✓[/green]" if found else "[yellow]✗[/yellow]"
        console.print(f"  {icon} {name:12s} — {desc}")

    # Check optional playwright
    try:
        import playwright  # noqa: F401

        console.print("  [green]✓[/green] playwright   — Browser automation (optional)")
    except ImportError:
        console.print(
            "  [yellow]✗[/yellow] playwright   — Browser automation"
            " (optional, pip install 'hydrofound[browser]')"
        )

    # Check API keys
    console.print("\n[bold]API Keys:[/bold]")
    keys = [
        ("HYDROFOUND_EXA_KEY", "Exa search"),
        ("HYDROFOUND_SEMANTIC_SCHOLAR_KEY", "Semantic Scholar"),
        ("HYDROFOUND_FIRECRAWL_KEY", "Firecrawl web scraping"),
    ]

    for key, _desc in keys:
        is_set = bool(os.environ.get(key))
        icon = "[green]✓[/green]" if is_set else "[yellow]✗[/yellow]"
        status = "set" if is_set else "not set"
        console.print(f"  {icon} {key:40s} — {status}")

    # KB stats
    if kb_path and (kb_path / ".hydrofound").exists():
        from hydrofound.catalog.index import CatalogIndex

        catalog = CatalogIndex(kb_path)
        stats = catalog.stats()

        console.print(f"\n[bold]Knowledge Base:[/bold] {kb_path}")
        console.print(f"  Papers:    {stats['papers']}")
        console.print(f"  Packages:  {stats['packages']}")
        console.print(f"  Codebases: {stats['codebases']}")

        topics = stats.get("topics", {})
        if topics:
            topic_str = ", ".join(f"{t} ({c})" for t, c in sorted(topics.items()))
            console.print(f"  Topics:    {topic_str}")
    elif kb_path:
        console.print(f"\n[yellow]KB not initialized at {kb_path}[/yellow]")
    else:
        console.print(
            "\n[dim]No --kb specified. Pass --kb to check knowledge base stats.[/dim]"
        )

    console.print()
