"""papermind api-diff CLI — compare package API versions."""

from __future__ import annotations

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def api_diff_cmd(
    ctx: typer.Context,
    old_name: str = typer.Argument(
        ..., help="Old package name in KB (e.g. 'pandas-2.1')."
    ),
    new_name: str = typer.Argument(
        ..., help="New package name in KB (e.g. 'pandas-3.0')."
    ),
    function: str = typer.Option(
        "", "--function", "-f", help="Filter to a specific function."
    ),
) -> None:
    """Compare two package API versions to find breaking changes.

    Requires both versions to be ingested under different names::

        papermind ingest package pandas --name pandas-2.1
        papermind ingest package pandas --name pandas-3.0
        papermind api-diff pandas-2.1 pandas-3.0
        papermind api-diff pandas-2.1 pandas-3.0 -f DataFrame.to_parquet
    """
    from papermind.api_diff import diff_apis, format_api_diff

    kb_path = _resolve_kb(ctx)

    try:
        result = diff_apis(kb_path, old_name, new_name, function_filter=function)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(format_api_diff(result))
