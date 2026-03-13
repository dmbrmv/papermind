"""hydrofound init command."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

console = Console()

DEFAULT_CONFIG = """\
[search]
qmd_path = "qmd"
node_path = "node"
fallback_search = true

[apis]
# Prefer environment variables (HYDROFOUND_*_KEY) over these values
semantic_scholar_key = ""
exa_key = ""

[ingestion]
marker_path = "marker"
marker_use_llm = false
default_paper_topic = "uncategorized"

[firecrawl]
api_key = ""

[privacy]
offline_only = false
"""

GITIGNORE = """\
# HydroFound internals
.hydrofound/config.toml
.hydrofound/qmd/
.hydrofound/last_search.json
"""


def init_command(
    path: Path = typer.Argument(
        default=None,
        help="Path to create the knowledge base. Default: ~/HydroFound",
    ),
) -> None:
    """Initialize a new HydroFound knowledge base."""
    if path is None:
        path = Path.home() / "HydroFound"

    path = path.resolve()

    if (path / ".hydrofound").exists():
        console.print(f"[red]Already initialized:[/red] {path}")
        raise typer.Exit(code=1)

    # Create directory structure
    for subdir in ["papers", "packages", "codebases", ".hydrofound"]:
        (path / subdir).mkdir(parents=True, exist_ok=True)

    # Write config
    (path / ".hydrofound" / "config.toml").write_text(DEFAULT_CONFIG)

    # Write .gitignore
    (path / ".gitignore").write_text(GITIGNORE)

    # Write empty catalog
    (path / "catalog.json").write_text(json.dumps([], indent=2) + "\n")

    # Write catalog.md
    (path / "catalog.md").write_text(
        "# HydroFound Knowledge Base\n\n"
        "> 0 papers | 0 packages | 0 codebases\n\n"
        "_Empty knowledge base. Run `hydrofound ingest` to add content._\n"
    )

    console.print(f"\n[green]HydroFound initialized at[/green] {path}\n")

    _print_quick_status()


def _print_quick_status() -> None:
    """Print a quick dependency status after init."""
    import shutil

    console.print("[bold]Dependencies:[/bold]")

    checks = [
        ("griffe", "griffe", "Python API extraction"),
        ("marker", "marker", "PDF conversion — pip install marker-pdf"),
        ("qmd", "qmd", "Semantic search — see github.com/tobi/qmd"),
    ]

    for name, cmd, desc in checks:
        found = shutil.which(cmd) is not None
        icon = "[green]✓[/green]" if found else "[yellow]✗[/yellow]"
        console.print(f"  {icon} {name} — {desc}")

    console.print("\n[bold]Quick start:[/bold]")
    console.print("  hydrofound ingest codebase /path/to/code --name myproject")
    console.print('  hydrofound search "function name"')
    console.print("  hydrofound catalog show\n")
