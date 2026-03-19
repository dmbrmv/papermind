"""papermind equation-map CLI — map paper equations to code variables."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def equation_map_cmd(
    ctx: typer.Context,
    code: str = typer.Argument(
        ...,
        help="Source file, optionally with ::function (e.g. model.py::calc_runoff).",
    ),
    equation: str = typer.Option(
        "",
        "--equation",
        "-e",
        help="LaTeX equation string to map. If omitted, uses --paper + --eq.",
    ),
    paper: str = typer.Option(
        "",
        "--paper",
        "-p",
        help="Paper ID to read equation from (requires --eq).",
    ),
    eq_num: str = typer.Option(
        "",
        "--eq",
        help="Equation number within the paper (e.g. '4.2').",
    ),
) -> None:
    """Map a paper equation's symbols to code variables.

    Uses heuristic matching (no LLM): exact, normalized, glossary, and
    fuzzy strategies. Shows proposed symbol→variable mappings and flags
    unmatched items on both sides.

    Examples::

        papermind equation-map model.py -e "Q = C \\cdot I \\cdot A"
        papermind equation-map model.py::calc_runoff -e "Q = K_s \\cdot S^{0.5}"
        papermind equation-map model.py --paper paper-green-ampt-1911 --eq 4.2
    """
    from papermind.equation_map import format_equation_map, map_equation_to_code

    # Parse file::function
    if "::" in code:
        file_str, func_name = code.rsplit("::", 1)
    else:
        file_str, func_name = code, None

    source_path = Path(file_str).resolve()
    if not source_path.is_file():
        console.print(f"[red]File not found:[/red] {source_path}")
        raise typer.Exit(code=1)

    # Get equation text
    latex = equation
    eq_number = eq_num

    if not latex and paper and eq_num:
        latex, eq_number = _load_equation_from_paper(ctx, paper, eq_num)
        if not latex:
            console.print(f"[red]Equation {eq_num} not found in paper {paper}[/red]")
            raise typer.Exit(code=1)
    elif not latex:
        console.print("[red]Provide --equation or --paper + --eq[/red]")
        raise typer.Exit(code=1)

    result = map_equation_to_code(
        latex,
        source_path,
        func_name,
        equation_number=eq_number,
    )
    console.print(format_equation_map(result))


def _load_equation_from_paper(
    ctx: typer.Context, paper_id: str, eq_num: str
) -> tuple[str, str]:
    """Load an equation from a paper's frontmatter by number."""
    import frontmatter as fm_lib

    kb_path = _resolve_kb(ctx)
    papers_dir = kb_path / "papers"
    if not papers_dir.exists():
        return "", ""

    for md_file in papers_dir.rglob("paper.md"):
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("id") != paper_id:
                continue
            equations = post.metadata.get("equations", [])
            for eq in equations:
                if eq.get("number") == eq_num:
                    return eq["latex"], eq_num
            return "", ""
        except Exception:
            continue

    return "", ""
