"""papermind report CLI — generate topic overview reports."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.markdown import Markdown

from papermind.cli.utils import _resolve_kb

console = Console()


def report_cmd(
    ctx: typer.Context,
    topic: str = typer.Option(
        ..., "--topic", "-t", help="Topic to generate report for."
    ),
    save: bool = typer.Option(
        False, "--save", help="Save report to reports/<topic>.md in the KB."
    ),
) -> None:
    """Generate a structured overview report for a KB topic.

    Scans all papers in the topic, extracts metadata, and produces a
    report with paper inventory, keyword taxonomy, equations catalog,
    and coverage analysis.

    Examples::

        papermind report --topic hydrology
        papermind report --topic hydrology --save
    """
    from papermind.report import generate_report

    kb_path = _resolve_kb(ctx)

    try:
        report = generate_report(kb_path, topic)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(Markdown(report))

    if save:
        report_dir = kb_path / "reports"
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / f"{topic}.md"
        report_path.write_text(report)
        console.print(f"\n[green]Saved to[/green] {report_path}")
