"""papermind reference CLI — find refs, analyze bib gaps, respond to reviewers."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def cite_cmd(
    ctx: typer.Context,
    claim: str = typer.Argument(..., help="Claim text to find references for."),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results."),
    no_external: bool = typer.Option(
        False, "--no-external", help="Search KB only, skip external APIs."
    ),
) -> None:
    """Find papers that support a specific claim.

    Searches the KB first, then widens to OpenAlex/Exa if coverage
    is thin. Returns ranked references with DOIs and abstracts.

    Examples::

        papermind cite "SWAT+ has been widely used for watershed modeling"
        papermind cite "CN method underestimates runoff in urban catchments"
    """
    from papermind.references import find_references, format_claim_result

    kb_path = _resolve_kb(ctx)
    result = find_references(
        claim,
        kb_path,
        max_results=limit,
        search_external=not no_external,
    )
    console.print(format_claim_result(result))


def bib_gap_cmd(
    ctx: typer.Context,
    draft: Path = typer.Argument(..., help="Path to paper draft (markdown)."),
    no_external: bool = typer.Option(False, "--no-external", help="KB only."),
) -> None:
    """Analyze a paper draft for claims missing citations.

    Scans the draft for factual claims without citations, searches
    for supporting papers, and reports gaps with suggestions.

    Examples::

        papermind bib-gap draft.md
        papermind bib-gap paper.md --no-external
    """
    from papermind.references import (
        analyze_bibliography_gaps,
        format_gap_analysis,
    )

    kb_path = _resolve_kb(ctx)
    resolved = draft.resolve()

    if not resolved.is_file():
        console.print(f"[red]Not a file:[/red] {resolved}")
        raise typer.Exit(code=1)

    results = analyze_bibliography_gaps(
        resolved, kb_path, search_external=not no_external
    )
    console.print(format_gap_analysis(results))


def respond_cmd(
    ctx: typer.Context,
    comment: str = typer.Argument(..., help="Reviewer comment or question."),
    no_external: bool = typer.Option(False, "--no-external", help="KB only."),
) -> None:
    """Find evidence to address a reviewer comment.

    Searches KB and external APIs for papers relevant to the
    reviewer's concern. Use the results to draft a response.

    Examples::

        papermind respond "You did not consider the impact of urbanization"
        papermind respond "What about model uncertainty?"
    """
    from papermind.references import (
        find_evidence_for_comment,
        format_claim_result,
    )

    kb_path = _resolve_kb(ctx)
    result = find_evidence_for_comment(
        comment, kb_path, search_external=not no_external
    )

    console.print("[bold]Reviewer comment:[/bold]")
    console.print(f"  {comment}\n")
    console.print("[bold]Evidence found:[/bold]")
    console.print(format_claim_result(result))
