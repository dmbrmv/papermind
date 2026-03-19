"""papermind session CLI — research session management."""

from __future__ import annotations

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()

session_app = typer.Typer(
    name="session",
    help="Research sessions — shared scratchpad for multi-agent workflows.",
    no_args_is_help=True,
)


@session_app.command(name="create")
def session_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Session name."),
) -> None:
    """Create a new research session.

    Examples::

        papermind session create "baseflow literature review"
    """
    from papermind.session import create_session

    kb_path = _resolve_kb(ctx)
    try:
        session = create_session(kb_path, name)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]Created session[/green] [bold]{session.name}[/bold] (`{session.id}`)"
    )


@session_app.command(name="add")
def session_add(
    ctx: typer.Context,
    session_id: str = typer.Argument(..., help="Session ID."),
    content: str = typer.Argument(..., help="Finding or note to add."),
    agent: str = typer.Option("user", "--agent", "-a", help="Agent name."),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags."),
) -> None:
    """Add an entry to a research session.

    Examples::

        papermind session add baseflow-lit-review "Found 3 papers on recession analysis" --agent sub-agent-1
        papermind session add baseflow-lit-review "Key finding: alpha_bf range 0.01-0.5" --tags key,parameter
    """
    from papermind.session import add_to_session

    kb_path = _resolve_kb(ctx)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    try:
        entry = add_to_session(kb_path, session_id, content, agent=agent, tags=tag_list)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Added[/green] entry by {entry.agent}")


@session_app.command(name="read")
def session_read(
    ctx: typer.Context,
    session_id: str = typer.Argument(..., help="Session ID."),
    tag: str = typer.Option("", "--tag", help="Filter entries by tag."),
) -> None:
    """Read a research session's accumulated findings.

    Examples::

        papermind session read baseflow-lit-review
        papermind session read baseflow-lit-review --tag key
    """
    from papermind.session import format_session, read_session

    kb_path = _resolve_kb(ctx)
    session = read_session(kb_path, session_id, tag=tag)

    if session is None:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise typer.Exit(code=1)

    console.print(format_session(session))


@session_app.command(name="list")
def session_list(ctx: typer.Context) -> None:
    """List all research sessions."""
    from papermind.session import format_session_list, list_sessions

    kb_path = _resolve_kb(ctx)
    sessions = list_sessions(kb_path)
    console.print(format_session_list(sessions))


@session_app.command(name="close")
def session_close(
    ctx: typer.Context,
    session_id: str = typer.Argument(..., help="Session ID to close."),
) -> None:
    """Close a research session (no more entries can be added)."""
    from papermind.session import close_session

    kb_path = _resolve_kb(ctx)
    session = close_session(kb_path, session_id)

    if session is None:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise typer.Exit(code=1)

    console.print(f"[green]Closed[/green] session [bold]{session.name}[/bold]")
