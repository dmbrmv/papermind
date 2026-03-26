"""papermind audit — freshness tracking and integrity checks."""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

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


def _print_integrity_table(findings: list) -> None:
    """Print integrity findings in a table."""
    table = Table(title="Integrity findings", show_header=True)
    table.add_column("Severity", style="bold")
    table.add_column("Code", style="cyan")
    table.add_column("Path", ratio=3)
    table.add_column("Message", ratio=4)

    for finding in findings:
        table.add_row(
            finding.severity,
            finding.code,
            finding.path or finding.paper_id or "—",
            finding.message,
        )

    console.print(table)


def _print_repair_table(actions: list) -> None:
    """Print proposed repair actions in a table."""
    table = Table(title="Repair plan", show_header=True)
    table.add_column("Confidence", style="bold")
    table.add_column("Code", style="cyan")
    table.add_column("Field", style="magenta")
    table.add_column("Path", ratio=3)
    table.add_column("Proposed", ratio=2)

    for action in actions:
        table.add_row(
            action.confidence,
            action.code,
            action.field,
            action.path or action.paper_id or "—",
            action.proposed_value,
        )

    console.print(table)


def _resolve_paper_path(kb: Path, paper_ref: str) -> tuple[Path | None, str]:
    """Resolve a paper path by relative path, id, or DOI."""
    from papermind.catalog.index import CatalogIndex

    path_candidate = kb / paper_ref
    if path_candidate.exists() and path_candidate.is_file():
        return path_candidate, "path"

    catalog = CatalogIndex(kb)
    entry = catalog.get(paper_ref)
    if entry and entry.type == "paper":
        full_path = kb / entry.path
        if full_path.exists():
            return full_path, "id"

    for item in catalog.entries:
        if item.type == "paper" and item.doi == paper_ref:
            full_path = kb / item.path
            if full_path.exists():
                return full_path, "doi"

    return None, "unknown"


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


@audit_app.command(name="integrity")
def audit_integrity(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Emit findings as JSON"),
    limit: int = typer.Option(50, "--limit", min=1, help="Maximum findings to print"),
    severity: str = typer.Option(
        "info",
        "--severity",
        help="Minimum severity to include (error, warning, info)",
    ),
    online: bool = typer.Option(
        False,
        "--online",
        help="Verify DOI/title consistency using online metadata lookup",
    ),
    fail_on: str = typer.Option(
        "error",
        "--fail-on",
        help="Exit non-zero on error, warning, or never",
    ),
) -> None:
    """Scan paper metadata and catalog state for integrity issues."""
    from papermind.integrity import (
        scan_kb_integrity,
        should_fail,
        summarize_findings,
    )

    severity_order = {"error": 0, "warning": 1, "info": 2}
    if severity not in severity_order:
        console.print("[red]Invalid severity[/red] — use error, warning, or info")
        raise typer.Exit(code=1)
    if fail_on not in {"error", "warning", "never"}:
        console.print("[red]Invalid fail-on[/red] — use error, warning, or never")
        raise typer.Exit(code=1)

    kb = _resolve_kb(ctx)
    findings = scan_kb_integrity(kb, online=online)
    findings = [f for f in findings if severity_order[f.severity] <= severity_order[severity]]
    summary = summarize_findings(findings)

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "summary": summary,
                    "findings": [finding.to_dict() for finding in findings],
                },
                indent=2,
            )
        )
    else:
        if findings:
            _print_integrity_table(findings[:limit])
            if len(findings) > limit:
                console.print(f"[dim]{len(findings) - limit} more finding(s) truncated[/dim]")
        else:
            console.print("[green]No integrity findings.[/green]")

        console.print(
            f"errors={summary['error']} warnings={summary['warning']} "
            f"info={summary['info']} total={summary['total']}"
        )

    if should_fail(findings, fail_on):
        raise typer.Exit(code=1)


@audit_app.command(name="health")
def audit_health(
    ctx: typer.Context,
    days: int = typer.Option(90, "--days", "-d", help="Freshness threshold in days"),
    online: bool = typer.Option(
        False,
        "--online",
        help="Verify DOI/title consistency using online metadata lookup",
    ),
    fail_on: str = typer.Option(
        "error",
        "--fail-on",
        help="Exit non-zero on error, warning, or never",
    ),
) -> None:
    """Print a combined freshness and integrity report."""
    import frontmatter as fm_lib

    from papermind.integrity import (
        scan_kb_integrity,
        should_fail,
        summarize_findings,
    )

    kb = _resolve_kb(ctx)
    cutoff = date.today() - timedelta(days=days)
    stale = 0

    for md_file in sorted((kb / "papers").rglob("*.md")) if (kb / "papers").exists() else []:
        try:
            post = fm_lib.load(md_file)
        except Exception:
            continue
        meta = post.metadata
        if meta.get("type") != "paper":
            continue
        verified = meta.get("last_verified", "")
        if not verified:
            stale += 1
            continue
        try:
            if date.fromisoformat(verified) < cutoff:
                stale += 1
        except ValueError:
            stale += 1

    findings = scan_kb_integrity(kb, online=online)
    summary = summarize_findings(findings)

    console.print("PaperMind Health")
    console.print("════════════════════════════════════════")
    console.print(f"Freshness: stale={stale} (threshold={days}d)")
    console.print(
        "Integrity: "
        f"errors={summary['error']} warnings={summary['warning']} "
        f"info={summary['info']} total={summary['total']}"
    )

    if should_fail(findings, fail_on):
        raise typer.Exit(code=1)


@audit_app.command(name="intake")
def audit_intake(
    ctx: typer.Context,
    paper_ref: str = typer.Argument(
        ...,
        help="Paper ID, KB-relative path, or DOI for the newly received paper",
    ),
    online: bool = typer.Option(
        True,
        "--online/--offline-lookups",
        help="Verify DOI/title consistency using OpenAlex",
    ),
    fail_on: str = typer.Option(
        "warning",
        "--fail-on",
        help="Exit non-zero on error, warning, or never",
    ),
) -> None:
    """Verify one ingested paper is structurally valid and trustworthy."""
    import frontmatter as fm_lib

    from papermind.catalog.index import CatalogIndex
    from papermind.integrity import (
        IntegrityFinding,
        _fetch_openalex_title,
        _title_similarity,
        should_fail,
        summarize_findings,
        validate_paper_metadata,
    )

    if fail_on not in {"error", "warning", "never"}:
        console.print("[red]Invalid fail-on[/red] — use error, warning, or never")
        raise typer.Exit(code=1)

    kb = _resolve_kb(ctx)
    paper_path, matched_via = _resolve_paper_path(kb, paper_ref)
    if paper_path is None:
        console.print(f"[red]Paper not found:[/red] {paper_ref!r}")
        raise typer.Exit(code=1)

    rel_path = str(paper_path.relative_to(kb))
    post = fm_lib.load(paper_path)
    meta = dict(post.metadata)
    findings = validate_paper_metadata(meta, path=rel_path)

    catalog = CatalogIndex(kb)
    entry = None
    for item in catalog.entries:
        if item.type == "paper" and item.path == rel_path:
            entry = item
            break

    if entry is None:
        findings.append(
            IntegrityFinding(
                severity="error",
                code="unindexed_paper_file",
                message="Paper file exists but is not registered in the catalog",
                path=rel_path,
                paper_id=str(meta.get("id", "")).strip(),
                title=str(meta.get("title", "")).strip(),
            )
        )

    doi = str(meta.get("doi", "")).strip()
    title = str(meta.get("title", "")).strip()
    if online and doi and title:
        remote_title = asyncio.run(_fetch_openalex_title(doi))
        if remote_title and _title_similarity(title, remote_title) < 0.45:
            findings.append(
                IntegrityFinding(
                    severity="warning",
                    code="doi_title_mismatch",
                    message="DOI resolves to a title that does not match local metadata",
                    path=rel_path,
                    paper_id=str(meta.get("id", "")).strip(),
                    title=title,
                    detail=f"doi={doi}; remote_title={remote_title}",
                )
            )

    summary = summarize_findings(findings)
    console.print("Paper intake verification")
    console.print("════════════════════════════════════════")
    console.print(f"Path: {rel_path}")
    console.print(f"Resolved via: {matched_via}")
    console.print(
        f"Integrity: errors={summary['error']} warnings={summary['warning']} "
        f"info={summary['info']} total={summary['total']}"
    )
    if findings:
        _print_integrity_table(findings)
    else:
        console.print("[green]Paper intake passed.[/green]")

    if should_fail(findings, fail_on):
        raise typer.Exit(code=1)


@audit_app.command(name="repair-plan")
def audit_repair_plan(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Emit repair plan as JSON"),
    limit: int = typer.Option(50, "--limit", min=1, help="Maximum actions to print"),
    min_confidence: str = typer.Option(
        "medium",
        "--min-confidence",
        help="Minimum confidence to include (high, medium, low)",
    ),
    online: bool = typer.Option(
        True,
        "--online/--offline-lookups",
        help="Use OpenAlex metadata lookups to build repair suggestions",
    ),
) -> None:
    """Build a structured repair plan for historical metadata issues."""
    from papermind.repair import plan_kb_repairs, summarize_actions

    if min_confidence not in {"high", "medium", "low"}:
        console.print("[red]Invalid min-confidence[/red] — use high, medium, or low")
        raise typer.Exit(code=1)

    threshold = {"high": 0, "medium": 1, "low": 2}
    kb = _resolve_kb(ctx)
    actions = plan_kb_repairs(kb, online=online)
    actions = [
        action
        for action in actions
        if threshold[action.confidence] <= threshold[min_confidence]
    ]
    summary = summarize_actions(actions)

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "summary": summary,
                    "actions": [action.to_dict() for action in actions],
                },
                indent=2,
            )
        )
        return

    if actions:
        _print_repair_table(actions[:limit])
        if len(actions) > limit:
            console.print(f"[dim]{len(actions) - limit} more action(s) truncated[/dim]")
    else:
        console.print("[green]No repair actions proposed.[/green]")

    console.print(
        f"high={summary['high']} medium={summary['medium']} "
        f"low={summary['low']} total={summary['total']}"
    )


@audit_app.command(name="repair-apply")
def audit_repair_apply(
    ctx: typer.Context,
    min_confidence: str = typer.Option(
        "high",
        "--min-confidence",
        help="Apply actions at or above this confidence (high, medium, low)",
    ),
    online: bool = typer.Option(
        True,
        "--online/--offline-lookups",
        help="Use OpenAlex metadata lookups to build repair suggestions",
    ),
) -> None:
    """Apply automated metadata repairs to the KB."""
    from papermind.repair import apply_repair_actions, plan_kb_repairs

    if min_confidence not in {"high", "medium", "low"}:
        console.print("[red]Invalid min-confidence[/red] — use high, medium, or low")
        raise typer.Exit(code=1)

    kb = _resolve_kb(ctx)
    actions = plan_kb_repairs(kb, online=online)
    applied = apply_repair_actions(kb, actions, min_confidence=min_confidence)
    console.print(f"Applied {applied} repair action(s)")


@audit_app.command(name="recover-deleted")
def audit_recover_deleted(
    ctx: typer.Context,
    source_report: str = typer.Option(
        "",
        "--source-report",
        help="Integrity report JSON that defines the deleted-paper recovery queue",
    ),
    state_file: str = typer.Option(
        "",
        "--state-file",
        help="Override the recovery state file path",
    ),
    min_similarity: float = typer.Option(
        0.9,
        "--min-similarity",
        min=0.0,
        max=1.0,
        help="Minimum title similarity required to attempt recovery",
    ),
    max_items: int = typer.Option(
        0,
        "--max-items",
        min=0,
        help="Maximum pending items to process in this run (0 = all pending)",
    ),
) -> None:
    """Recover deleted papers sequentially from a prior integrity report."""
    from papermind.recovery import (
        default_recovery_state_path,
        recovery_summary,
        run_deleted_paper_recovery,
    )

    kb = _resolve_kb(ctx)
    resolved_report = (
        Path(source_report).resolve()
        if source_report
        else kb / ".papermind" / "reports" / "integrity_online_post_repair_2026-03-26.json"
    )
    resolved_state = Path(state_file).resolve() if state_file else default_recovery_state_path(kb)

    state = run_deleted_paper_recovery(
        kb,
        resolved_report,
        state_path=resolved_state,
        min_similarity=min_similarity,
        max_items=max_items,
    )
    summary = recovery_summary(state)
    console.print("Deleted-paper recovery")
    console.print("════════════════════════════════════════")
    console.print(f"State file: {resolved_state}")
    console.print(
        f"pending={summary['pending']} restored={summary['restored']} "
        f"skipped={summary['skipped']} failed={summary['failed']} total={summary['total']}"
    )


@audit_app.command(name="recover-status")
def audit_recover_status(
    ctx: typer.Context,
    state_file: str = typer.Option(
        "",
        "--state-file",
        help="Override the recovery state file path",
    ),
) -> None:
    """Show the current deleted-paper recovery state."""
    from papermind.recovery import (
        default_recovery_state_path,
        load_recovery_state,
        recovery_summary,
    )

    kb = _resolve_kb(ctx)
    resolved_state = Path(state_file).resolve() if state_file else default_recovery_state_path(kb)
    state = load_recovery_state(kb, state_path=resolved_state)
    summary = recovery_summary(state)

    console.print("Deleted-paper recovery status")
    console.print("════════════════════════════════════════")
    console.print(f"State file: {resolved_state}")
    console.print(f"Source report: {state.get('source_report', '')}")
    if state.get("last_run_started_at"):
        console.print(f"Last run started: {state.get('last_run_started_at', '')}")
    if state.get("last_run_finished_at"):
        console.print(f"Last run finished: {state.get('last_run_finished_at', '')}")
    console.print(
        f"pending={summary['pending']} restored={summary['restored']} "
        f"skipped={summary['skipped']} failed={summary['failed']} total={summary['total']}"
    )
    if state.get("pending"):
        next_item = state["pending"][0]
        console.print(f"Next pending: {next_item.get('title', '')}")


@audit_app.command(name="recover-retry")
def audit_recover_retry(
    ctx: typer.Context,
    retry: str = typer.Option(
        "failed",
        "--retry",
        help=(
            "What to requeue: failed, skipped, all, or a comma-separated list of "
            "reason classes such as download_failed,ingest_failed"
        ),
    ),
    state_file: str = typer.Option(
        "",
        "--state-file",
        help="Override the recovery state file path",
    ),
) -> None:
    """Requeue selected deleted-paper recovery outcomes back into pending."""
    from papermind.recovery import (
        default_recovery_state_path,
        recovery_summary,
        requeue_recovery_items,
        retryable_failure_classes,
    )

    kb = _resolve_kb(ctx)
    resolved_state = Path(state_file).resolve() if state_file else default_recovery_state_path(kb)

    include_failed = retry in {"failed", "all"} or "," in retry
    include_skipped = retry in {"skipped", "all"} or "," in retry

    if retry in {"failed", "skipped", "all"}:
        retry_classes = retryable_failure_classes()
    else:
        retry_classes = {part.strip() for part in retry.split(",") if part.strip()}
        unknown = retry_classes - retryable_failure_classes()
        if unknown:
            console.print(
                "[red]Unknown retry class(es):[/red] "
                + ", ".join(sorted(unknown))
            )
            raise typer.Exit(code=1)

    state = requeue_recovery_items(
        kb,
        state_path=resolved_state,
        retry_classes=retry_classes,
        include_skipped=include_skipped,
        include_failed=include_failed,
    )
    summary = recovery_summary(state)
    console.print("Deleted-paper recovery retry")
    console.print("════════════════════════════════════════")
    console.print(f"State file: {resolved_state}")
    console.print(
        f"pending={summary['pending']} restored={summary['restored']} "
        f"skipped={summary['skipped']} failed={summary['failed']} total={summary['total']}"
    )
