"""papermind verify CLI — check code implements paper equations correctly."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def verify_cmd(
    ctx: typer.Context,
    code: str = typer.Argument(
        ...,
        help="Source file, optionally with ::function (e.g. model.py::calc_runoff).",
    ),
    paper: str = typer.Option(..., "--paper", "-p", help="Paper ID in the KB."),
    eq: str = typer.Option(..., "--eq", "-e", help="Equation number (e.g. '4.2')."),
) -> None:
    """Verify that code implements a paper equation correctly.

    Combines equation-to-code mapping with provenance scanning to
    produce a structured verification report with coverage score,
    symbol mappings, and gaps.

    Examples::

        papermind verify model.py::calc_runoff --paper paper-scs-cn-1986 --eq 2.1
        papermind verify solver.f90 --paper paper-green-ampt-1911 --eq 4.2
    """
    from papermind.verify import format_verification, verify_implementation

    kb_path = _resolve_kb(ctx)

    # Parse file::function
    if "::" in code:
        file_str, func_name = code.rsplit("::", 1)
    else:
        file_str, func_name = code, None

    source_path = Path(file_str).resolve()
    if not source_path.is_file():
        console.print(f"[red]File not found:[/red] {source_path}")
        raise typer.Exit(code=1)

    result = verify_implementation(paper, eq, source_path, func_name, kb_path)
    console.print(format_verification(result))

    if result.verdict == "poor":
        raise typer.Exit(code=1)
