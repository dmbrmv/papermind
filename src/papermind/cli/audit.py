"""papermind audit — freshness tracking and staleness checks."""

from __future__ import annotations

from datetime import date, timedelta

import typer
from rich.console import Console
from rich.table import Table

from papermind.cli.utils import _resolve_kb

console = Console()

audit_app = typer.Typer(
    name="audit",
    help="Freshness tracking and knowledge base audits.",
    no_args_is_help=True,
)


@audit_app.command(name="stale")
def audit_stale(
    ctx: typer.Context,
    days: int = typer.Option(
        90, "--days", "-d", help="Flag entries not verified in N days"
    ),
) -> None:
    """List entries that haven't been verified recently.

    Papers with a ``last_verified`` date older than ``--days`` are
    flagged.  Papers without ``last_verified`` are always flagged.
    """
    import frontmatter as fm_lib

    kb = _resolve_kb(ctx)
    cutoff = date.today() - timedelta(days=days)
    stale: list[tuple[str, str, str]] = []  # (id, title, reason)

    for md_file in sorted(kb.rglob("*.md")):
        if (
            md_file.name.startswith(".")
            or ".papermind" in md_file.parts
            or md_file.name == "catalog.md"
        ):
            continue
        try:
            post = fm_lib.load(md_file)
            meta = post.metadata
            if meta.get("type") != "paper":
                continue
            pid = meta.get("id", md_file.stem)
            title = meta.get("title", "")[:50]
            verified = meta.get("last_verified", "")

            if not verified:
                stale.append((pid, title, "never verified"))
            else:
                try:
                    vdate = date.fromisoformat(verified)
                    if vdate < cutoff:
                        stale.append((pid, title, f"verified {verified}"))
                except ValueError:
                    stale.append((pid, title, f"bad date: {verified}"))
        except Exception:
            continue

    if not stale:
        console.print(f"[green]All papers verified within {days} days.[/green]")
        raise typer.Exit(code=0)

    table = Table(
        title=f"Stale papers (>{days} days)",
        show_header=True,
    )
    table.add_column("ID", style="cyan", ratio=3)
    table.add_column("Title", ratio=3)
    table.add_column("Status", style="yellow", ratio=2)

    for pid, title, reason in stale:
        table.add_row(pid[:40], title, reason)

    console.print(table)
    console.print(f"\n[bold]{len(stale)} stale paper(s)[/bold]")


@audit_app.command(name="verify")
def audit_verify(
    ctx: typer.Context,
    paper_id: str = typer.Argument(..., help="Paper ID to mark as verified"),
    note: str = typer.Option("", "--note", help="Verification note"),
) -> None:
    """Mark a paper as verified today.

    Sets the ``last_verified`` field in frontmatter to today's date.
    """
    import frontmatter as fm_lib

    kb = _resolve_kb(ctx)

    for md_file in kb.rglob("*.md"):
        if (
            md_file.name.startswith(".")
            or ".papermind" in md_file.parts
            or md_file.name == "catalog.md"
        ):
            continue
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("id") == paper_id:
                post.metadata["last_verified"] = date.today().isoformat()
                if note:
                    post.metadata["verification_note"] = note
                md_file.write_text(fm_lib.dumps(post))
                console.print(
                    f"[green]Verified[/green] {paper_id} ({date.today().isoformat()})"
                )
                return
        except Exception:
            continue

    console.print(f"[red]Paper not found:[/red] {paper_id!r}")
    raise typer.Exit(code=1)


@audit_app.command(name="check-versions")
def audit_check_versions(ctx: typer.Context) -> None:
    """Check if indexed packages have newer versions on PyPI."""
    import httpx

    from papermind.catalog.index import CatalogIndex

    kb = _resolve_kb(ctx)
    catalog = CatalogIndex(kb)

    packages = [e for e in catalog.entries if e.type == "package"]
    if not packages:
        console.print("[dim]No packages in KB.[/dim]")
        raise typer.Exit(code=0)

    for entry in packages:
        name = entry.title
        try:
            resp = httpx.get(f"https://pypi.org/pypi/{name}/json", timeout=10)
            if resp.status_code == 200:
                latest = resp.json()["info"]["version"]
                console.print(f"  {name:30s} latest: [bold]{latest}[/bold]")
            else:
                console.print(f"  {name:30s} [dim]not on PyPI[/dim]")
        except Exception:
            console.print(f"  {name:30s} [red]lookup failed[/red]")
