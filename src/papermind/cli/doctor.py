"""papermind doctor — dependency health check."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def doctor_command(
    ctx: typer.Context,
) -> None:
    """Check PaperMind dependencies and configuration."""
    kb_path = ctx.obj.get("kb") if ctx.obj else None

    console.print("\n[bold]PaperMind Doctor[/bold]")
    console.print("═" * 40)

    # Check dependencies
    console.print("\n[bold]Dependencies:[/bold]")
    deps = [
        ("griffe", "griffe", "Python API extraction"),
        ("qmd", "qmd", "Semantic search — github.com/tobi/qmd"),
        ("node", "node", "Required by qmd (node >= 22)"),
    ]

    for name, cmd, desc in deps:
        found = shutil.which(cmd) is not None
        icon = "[green]✓[/green]" if found else "[yellow]✗[/yellow]"
        console.print(f"  {icon} {name:12s} — {desc}")

    # Check GLM-OCR (default PDF converter)
    from papermind.ingestion.glm_ocr import is_available as glm_ocr_available

    if glm_ocr_available():
        console.print(
            "  [green]✓[/green] glm-ocr      "
            "— PDF conversion (transformers + torch + pymupdf)"
        )
    else:
        console.print(
            "  [yellow]✗[/yellow] glm-ocr      — PDF conversion"
            " — pip install 'papermind[ocr]'"
        )

    # Check optional playwright
    try:
        import playwright  # noqa: F401

        console.print("  [green]✓[/green] playwright   — Browser automation (optional)")
    except ImportError:
        console.print(
            "  [yellow]✗[/yellow] playwright   — Browser automation"
            " (optional, pip install 'papermind[browser]')"
        )

    # Check API keys
    console.print("\n[bold]API Keys:[/bold]")
    keys = [
        ("PAPERMIND_EXA_KEY", "Exa search"),
        ("PAPERMIND_SEMANTIC_SCHOLAR_KEY", "Semantic Scholar"),
        ("PAPERMIND_FIRECRAWL_KEY", "Firecrawl web scraping"),
        ("PAPERMIND_ZAI_API_KEY", "Z.AI OCR"),
    ]

    for key, _desc in keys:
        is_set = bool(os.environ.get(key))
        icon = "[green]✓[/green]" if is_set else "[yellow]✗[/yellow]"
        status = "set" if is_set else "not set"
        console.print(f"  {icon} {key:40s} — {status}")

    # KB stats
    if kb_path and (kb_path / ".papermind").exists():
        from papermind.catalog.index import CatalogIndex
        from papermind.config import load_config
        from papermind.recovery import default_recovery_state_path, recovery_summary

        config = load_config(Path(kb_path))
        catalog = CatalogIndex(kb_path)
        stats = catalog.stats()

        console.print(f"\n[bold]Knowledge Base:[/bold] {kb_path}")
        console.print(f"  Papers:    {stats['papers']}")
        console.print(f"  Packages:  {stats['packages']}")
        console.print(f"  Codebases: {stats['codebases']}")
        console.print(f"  OCR:       {config.ocr_backend}")

        topics = stats.get("topics", {})
        if topics:
            topic_str = ", ".join(f"{t} ({c})" for t, c in sorted(topics.items()))
            console.print(f"  Topics:    {topic_str}")

        recovery_state = default_recovery_state_path(kb_path)
        console.print("\n[bold]Recovery:[/bold]")
        if recovery_state.exists():
            import json

            state = json.loads(recovery_state.read_text())
            summary = recovery_summary(state)
            console.print(f"  State:     {recovery_state}")
            console.print(
                f"  Queue:     pending={summary['pending']} restored={summary['restored']} "
                f"skipped={summary['skipped']} failed={summary['failed']}"
            )
            if state.get("last_run_started_at"):
                console.print(f"  Started:   {state.get('last_run_started_at', '')}")
            if state.get("last_run_finished_at"):
                console.print(f"  Finished:  {state.get('last_run_finished_at', '')}")
        else:
            console.print("  State:     none")
    elif kb_path:
        console.print(f"\n[yellow]KB not initialized at {kb_path}[/yellow]")
    else:
        console.print(
            "\n[dim]No --kb specified. Pass --kb to check knowledge base stats.[/dim]"
        )

    console.print()
