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
ocr_model = "zai-org/GLM-OCR"   # HuggingFace model for PDF OCR
ocr_dpi = 150                    # DPI for PDF page rendering
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
    ctx: typer.Context,
    path: Path = typer.Argument(
        default=None,
        help="Path to create the knowledge base. Default: ~/HydroFound",
    ),
) -> None:
    """Initialize a new HydroFound knowledge base."""
    # Prefer --kb global option, then positional arg, then default
    kb_from_ctx = ctx.obj.get("kb") if ctx.obj else None
    if path is None and kb_from_ctx is not None:
        path = kb_from_ctx
    elif path is None:
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

    from hydrofound.ingestion.glm_ocr import is_available as glm_ocr_ok

    checks = [
        ("griffe", shutil.which("griffe") is not None, "Python API extraction"),
        ("glm-ocr", glm_ocr_ok(), "PDF conversion — pip install 'hydrofound[ocr]'"),
        (
            "qmd",
            shutil.which("qmd") is not None,
            "Semantic search — see github.com/tobi/qmd",
        ),
    ]

    for name, found, desc in checks:
        icon = "[green]✓[/green]" if found else "[yellow]✗[/yellow]"
        console.print(f"  {icon} {name} — {desc}")

    console.print("\n[bold]Quick start:[/bold]")
    console.print("  hydrofound ingest codebase /path/to/code --name myproject")
    console.print('  hydrofound search "function name"')
    console.print("  hydrofound catalog show\n")
