"""hydrofound ingest CLI — ingest codebases, packages, and papers into the KB."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

ingest_app = typer.Typer(
    name="ingest",
    help="Ingest content into the knowledge base.",
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


@ingest_app.command(name="codebase")
def ingest_codebase(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Path to the codebase directory."),
    name: str = typer.Option(..., "--name", help="Name for this codebase in the KB."),
    no_reindex: bool = typer.Option(
        False,
        "--no-reindex",
        help="Skip qmd reindex after ingestion.",
    ),
) -> None:
    """Ingest a codebase directory into the knowledge base.

    Walks the codebase, extracts signatures, renders markdown files into
    kb/codebases/<name>/, and updates catalog.json and catalog.md.
    """
    from datetime import date

    from hydrofound.catalog.index import CatalogEntry, CatalogIndex
    from hydrofound.catalog.render import render_catalog_md
    from hydrofound.ingestion.codebase import walk_codebase
    from hydrofound.ingestion.codebase_render import render_codebase

    kb_path = _resolve_kb(ctx)
    codebase_path = path.resolve()

    if not codebase_path.is_dir():
        console.print(f"[red]Not a directory:[/red] {codebase_path}")
        raise typer.Exit(code=1)

    console.print(f"Walking codebase: [bold]{codebase_path}[/bold]")
    cb = walk_codebase(codebase_path)
    # Override the name from --name option
    cb.name = name

    output_dir = kb_path / "codebases" / name
    console.print(f"Rendering to: [bold]{output_dir}[/bold]")
    created = render_codebase(cb, output_dir)

    # Build catalog entry
    entry = CatalogEntry(
        id=f"codebase-{name}",
        type="codebase",
        path=f"codebases/{name}/_index.md",
        title=name,
        files=[str(p.relative_to(kb_path)) for p in created],
        added=date.today().isoformat(),
        updated=date.today().isoformat(),
    )

    catalog = CatalogIndex(kb_path)
    catalog.add(entry)

    # Regenerate catalog.md
    (kb_path / "catalog.md").write_text(render_catalog_md(catalog.entries))

    console.print(f"[green]Ingested[/green] codebase [bold]{name}[/bold]")
    console.print(f"  Files written: {len(created)}")
    console.print(f"  Languages detected: {', '.join(sorted(cb.languages)) or 'none'}")
    console.print(f"  Source files: {len(cb.file_tree)}")

    if not no_reindex:
        _try_qmd_reindex(kb_path)


@ingest_app.command(name="paper")
def ingest_paper_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(
        ..., help="Path to a PDF file or a directory of PDFs (batch mode)."
    ),
    topic: str = typer.Option(
        "uncategorized",
        "--topic",
        "-t",
        help="Topic category for the paper(s).",
    ),
    no_reindex: bool = typer.Option(
        False,
        "--no-reindex",
        help="Skip qmd reindex after ingestion.",
    ),
) -> None:
    """Ingest a PDF paper (or a folder of PDFs) into the knowledge base.

    When *path* is a directory, all ``*.pdf`` files found recursively are
    ingested.  Duplicates (by DOI) are skipped; individual failures are logged
    but do not abort the batch.  A single reindex is issued at the end.

    When *path* is a file, a single paper is ingested (original behaviour).
    """
    from hydrofound.config import load_config
    from hydrofound.ingestion.paper import ingest_paper, ingest_papers_batch

    kb_path = _resolve_kb(ctx)
    resolved = path.resolve()

    if not resolved.exists():
        console.print(f"[red]Path not found:[/red] {resolved}")
        raise typer.Exit(code=1)

    config = load_config(kb_path)

    # ---- Batch mode (directory) ------------------------------------------------
    if resolved.is_dir():
        result = ingest_papers_batch(resolved, topic, kb_path, config)
        console.print(
            f"[green]Batch complete[/green]: "
            f"[bold]{result.ingested}[/bold] ingested, "
            f"[yellow]{result.skipped}[/yellow] skipped, "
            f"[red]{result.failed}[/red] failed"
        )
        for pdf_path, error in result.errors.items():
            console.print(f"  [red]ERROR[/red] {pdf_path.name}: {error}")
        return

    # ---- Single-file mode ------------------------------------------------------
    try:
        entry = ingest_paper(
            resolved,
            topic,
            kb_path,
            config,
            no_reindex=no_reindex,
        )
    except FileNotFoundError as exc:
        console.print(f"[red]Marker not installed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        console.print(f"[red]Ingestion failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if entry is None:
        console.print(
            "[yellow]Skipped[/yellow] — a paper with the same DOI already exists."
        )
        raise typer.Exit(code=0)

    console.print(f"[green]Ingested[/green] paper [bold]{entry.title}[/bold]")
    console.print(f"  ID:    {entry.id}")
    console.print(f"  Topic: {entry.topic}")
    if entry.doi:
        console.print(f"  DOI:   {entry.doi}")
    console.print(f"  Path:  {entry.path}")


def _try_qmd_reindex(kb_path: Path) -> None:
    """Attempt to run qmd reindex; skip silently if qmd is not installed."""
    import shutil
    import subprocess

    if shutil.which("qmd") is None:
        return

    try:
        subprocess.run(
            ["qmd", "reindex", str(kb_path)],
            check=False,
            capture_output=True,
        )
    except OSError:
        pass
