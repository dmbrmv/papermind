"""HydroFound CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(
    name="hydrofound",
    help="Scientific knowledge base — papers, packages, codebases → queryable markdown.",
    no_args_is_help=True,
)

console = Console()


def kb_path_option(value: str | None = None) -> Path | None:
    """Resolve --kb option to a Path."""
    if value is None:
        return None
    return Path(value).resolve()


@app.callback()
def main_callback(
    ctx: typer.Context,
    kb: str = typer.Option(None, "--kb", help="Path to HydroFound knowledge base"),
    offline: bool = typer.Option(False, "--offline", help="Disable all network access"),
) -> None:
    """Global options."""
    ctx.ensure_object(dict)
    ctx.obj["kb"] = Path(kb).resolve() if kb else None
    ctx.obj["offline"] = offline


from hydrofound.cli.catalog import catalog_app, remove_command  # noqa: E402
from hydrofound.cli.discover import discover_cmd  # noqa: E402
from hydrofound.cli.doctor import doctor_command  # noqa: E402
from hydrofound.cli.download import download_cmd  # noqa: E402
from hydrofound.cli.ingest import ingest_app  # noqa: E402
from hydrofound.cli.init import init_command  # noqa: E402
from hydrofound.cli.search import search_command  # noqa: E402

app.command(name="init")(init_command)
app.add_typer(ingest_app, name="ingest")
app.command(name="search")(search_command)
app.add_typer(catalog_app, name="catalog")
app.command(name="remove")(remove_command)
app.command(name="discover")(discover_cmd)
app.command(name="download")(download_cmd)
app.command(name="doctor")(doctor_command)


@app.command(name="reindex")
def reindex_command(ctx: typer.Context) -> None:
    """Rebuild catalog from filesystem and regenerate catalog.md."""
    kb_path = ctx.obj.get("kb") if ctx.obj else None
    if not kb_path or not (kb_path / ".hydrofound").exists():
        typer.echo("Error: --kb required and must point to initialized KB", err=True)
        raise typer.Exit(code=1)

    from hydrofound.catalog.index import CatalogIndex
    from hydrofound.catalog.render import render_catalog_md

    # Rebuild catalog.json from frontmatter (filesystem is truth)
    catalog = CatalogIndex.rebuild(kb_path)

    # Regenerate catalog.md
    (kb_path / "catalog.md").write_text(render_catalog_md(catalog.entries))

    # Trigger qmd reindex if available (best-effort)
    from hydrofound.query.qmd import qmd_reindex

    qmd_reindex(kb_path)

    console.print(f"Reindexed: {len(catalog.entries)} entries")


@app.command(name="serve")
def serve_command(
    ctx: typer.Context,
) -> None:
    """Start the MCP server (stdio transport)."""
    import asyncio

    from mcp.server.stdio import stdio_server

    from hydrofound.mcp_server import create_server

    kb_path = ctx.obj.get("kb") if ctx.obj else None
    if not kb_path:
        typer.echo("Error: --kb required for serve command", err=True)
        raise typer.Exit(code=1)

    server = create_server(kb_path)

    async def run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(run())


@app.command()
def version() -> None:
    """Print version."""
    from hydrofound import __version__

    typer.echo(f"hydrofound {__version__}")
