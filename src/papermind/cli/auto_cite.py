"""papermind auto-cite CLI — find refs with auto-ingest."""

from __future__ import annotations

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def auto_cite_cmd(
    ctx: typer.Context,
    claim: str = typer.Argument(..., help="Claim to find references for."),
    topic: str = typer.Option(
        "uncategorized", "--topic", "-t", help="Topic for auto-ingested papers."
    ),
    limit: int = typer.Option(5, "--limit", "-n", help="Max total results."),
    max_ingest: int = typer.Option(
        3, "--max-ingest", help="Max papers to auto-ingest."
    ),
    no_external: bool = typer.Option(
        False, "--no-external", help="KB only, skip external search."
    ),
) -> None:
    """Find references with automatic discovery and ingestion.

    Searches the KB first. If coverage is thin, discovers papers via
    OpenAlex/Exa, downloads PDFs, ingests them into the KB, and returns
    all references. The KB grows from your questions.

    Examples::

        papermind auto-cite "SWAT+ is widely used for watershed modeling"
        papermind auto-cite "CN method underestimates urban runoff" -t hydrology
        papermind auto-cite "deep learning for streamflow" --max-ingest 5
    """
    from papermind.auto_cite import auto_cite, format_auto_cite

    kb_path = _resolve_kb(ctx)

    if no_external:
        # Just do KB search, no auto-ingest
        from papermind.references import find_references, format_claim_result

        result = find_references(claim, kb_path, search_external=False)
        console.print(format_claim_result(result))
        return

    result = auto_cite(
        claim,
        kb_path,
        topic=topic,
        max_results=limit,
        max_ingest=max_ingest,
    )
    console.print(format_auto_cite(result))

    if result.newly_ingested:
        console.print(
            f"\n[green]{len(result.newly_ingested)} paper(s) "
            f"auto-ingested into topic '{topic}'[/green]"
        )
