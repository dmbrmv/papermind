"""papermind ingest CLI — ingest codebases, packages, and papers into the KB."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb
from papermind.ingestion.validation import ValidationError

ingest_app = typer.Typer(
    name="ingest",
    help="Ingest content into the knowledge base.",
    no_args_is_help=True,
)

console = Console()


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

    from papermind.catalog.index import CatalogEntry, CatalogIndex
    from papermind.catalog.render import render_catalog_md
    from papermind.ingestion.codebase import walk_codebase
    from papermind.ingestion.codebase_render import render_codebase

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
    # Remove old entry if re-ingesting
    if catalog.get(entry.id):
        catalog.remove(entry.id)
    catalog.add(entry)

    # Regenerate catalog.md
    (kb_path / "catalog.md").write_text(render_catalog_md(catalog.entries))

    console.print(f"[green]Ingested[/green] codebase [bold]{name}[/bold]")
    console.print(f"  Files written: {len(created)}")
    console.print(f"  Languages detected: {', '.join(sorted(cb.languages)) or 'none'}")
    console.print(f"  Source files: {len(cb.file_tree)}")

    if not no_reindex:
        from papermind.query.qmd import qmd_reindex

        qmd_reindex(kb_path)


@ingest_app.command(name="paper")
def ingest_paper_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(
        ...,
        help=("Path to a PDF or markdown file, or a directory of papers (batch mode)."),
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
    """Ingest a paper (PDF or markdown) into the knowledge base.

    Accepts ``.pdf``, ``.md``, and ``.markdown`` files.  Markdown files are
    ingested directly — no OCR needed.  Existing YAML frontmatter in markdown
    files is respected (title, DOI, year, abstract).

    When *path* is a directory, all supported files found recursively are
    ingested.  Duplicates (by DOI or title similarity) are skipped; individual
    failures are logged but do not abort the batch.
    """
    from papermind.config import load_config
    from papermind.ingestion.paper import ingest_paper, ingest_papers_batch

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
        for err_path, error in result.errors.items():
            console.print(f"  [red]ERROR[/red] {err_path.name}: {error}")
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
    except ImportError as exc:
        console.print(f"[red]OCR not installed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except (RuntimeError, ValidationError) as exc:
        console.print(f"[red]Ingestion failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if entry is None:
        console.print(
            "[yellow]Skipped[/yellow] — a paper with the same DOI or title already exists."
        )
        raise typer.Exit(code=0)

    console.print(f"[green]Ingested[/green] paper [bold]{entry.title}[/bold]")
    console.print(f"  ID:    {entry.id}")
    console.print(f"  Topic: {entry.topic}")
    if entry.doi:
        console.print(f"  DOI:   {entry.doi}")
    console.print(f"  Path:  {entry.path}")


@ingest_app.command(name="package")
def ingest_package_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Python package name"),
    from_git: str = typer.Option(
        "",
        "--from-git",
        help="Clone a git repo and extract the package from it.",
    ),
    source_path: str = typer.Option(
        "",
        "--source-path",
        help="Local path containing the package source (added to griffe search paths).",
    ),
    docs_url: str = typer.Option("", "--docs-url", help="Documentation URL to crawl."),
    no_reindex: bool = typer.Option(
        False,
        "--no-reindex",
        help="Skip qmd reindex after ingestion.",
    ),
) -> None:
    """Ingest a Python package's API and documentation.

    Extracts the public API via griffe (static analysis), optionally fetches
    web docs via Firecrawl or plain HTTP, and writes the result into
    kb/packages/<name>/. catalog.json and catalog.md are updated.

    For packages not installed locally, use ``--from-git`` to clone a
    repository or ``--source-path`` to point at a local checkout::

        papermind ingest package lisflood --from-git https://github.com/ec-jrc/lisflood-code.git
        papermind ingest package lisflood --source-path /tmp/lisflood-code/src
    """
    import shutil
    import tempfile

    from papermind.config import load_config
    from papermind.ingestion.package import ingest_package

    kb_path = _resolve_kb(ctx)
    config = load_config(kb_path)

    offline: bool = ctx.obj.get("offline", False) if ctx.obj else False
    if offline:
        config.offline_only = True

    # Resolve search paths for griffe
    search_paths: list[Path] = []
    clone_dir: Path | None = None

    if from_git:
        if offline:
            console.print("[red]Error:[/red] --from-git requires network")
            raise typer.Exit(code=1)
        clone_dir = Path(tempfile.mkdtemp(prefix="papermind-git-"))
        console.print(f"[dim]Cloning {from_git}...[/dim]")
        import subprocess

        result = subprocess.run(
            ["git", "clone", "--depth", "1", from_git, str(clone_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"[red]Clone failed:[/red] {result.stderr}")
            shutil.rmtree(clone_dir, ignore_errors=True)
            raise typer.Exit(code=1)
        # Auto-detect src/ layout or root package
        if (clone_dir / "src").is_dir():
            search_paths.append(clone_dir / "src")
        else:
            search_paths.append(clone_dir)

    if source_path:
        sp = Path(source_path).resolve()
        if not sp.is_dir():
            console.print(f"[red]Not a directory:[/red] {sp}")
            raise typer.Exit(code=1)
        search_paths.append(sp)

    try:
        entry = ingest_package(
            name,
            kb_path,
            config,
            docs_url=docs_url,
            no_reindex=no_reindex,
            search_paths=search_paths or None,
        )
    except Exception as exc:
        console.print(f"[red]Ingestion failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        if clone_dir and clone_dir.exists():
            shutil.rmtree(clone_dir, ignore_errors=True)

    console.print(f"[green]Ingested[/green] package [bold]{name}[/bold]")
    console.print(f"  ID:    {entry.id}")
    console.print(f"  Files: {', '.join(entry.files)}")
    if entry.source_url:
        console.print(f"  Docs:  {entry.source_url}")

    if not no_reindex:
        from papermind.query.qmd import qmd_reindex

        qmd_reindex(kb_path)
