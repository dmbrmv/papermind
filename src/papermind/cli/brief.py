"""papermind brief — commit-triggered knowledge surfacing."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import typer
from rich.console import Console

from papermind.cli.utils import _resolve_kb

console = Console()


def brief_cmd(
    ctx: typer.Context,
    diff: str = typer.Option(
        "HEAD~1..HEAD",
        "--diff",
        "-d",
        help="Git diff range (e.g. HEAD~1..HEAD, main..feature)",
    ),
    repo: str = typer.Option(
        ".",
        "--repo",
        "-r",
        help="Path to git repository to read diff from",
    ),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results"),
) -> None:
    """Surface relevant KB entries for recent code changes.

    Reads a git diff, extracts concepts from changed code, and
    searches the KB. Designed for post-commit knowledge surfacing.

    Examples::

        papermind brief --diff HEAD~1..HEAD
        papermind brief --diff main..feature --repo ~/project
    """
    from papermind.query.fallback import fallback_search
    from papermind.watch import check_pitfalls

    kb = _resolve_kb(ctx)
    repo_path = Path(repo).resolve()

    # Get the diff
    try:
        result = subprocess.run(
            ["git", "diff", diff, "--unified=0", "--no-color"],
            capture_output=True,
            text=True,
            cwd=repo_path,
        )
        if result.returncode != 0:
            console.print(f"[red]git diff failed:[/red] {result.stderr}")
            raise typer.Exit(code=1)
    except FileNotFoundError:
        console.print("[red]git not found[/red]")
        raise typer.Exit(code=1)

    diff_text = result.stdout
    if not diff_text:
        console.print("[dim]No changes in diff range.[/dim]")
        raise typer.Exit(code=0)

    # Extract concepts from the diff
    concepts = _extract_diff_concepts(diff_text)
    if not concepts:
        console.print("[dim]No searchable concepts in diff.[/dim]")
        raise typer.Exit(code=0)

    query = " ".join(concepts[:30])

    # Search KB
    results = fallback_search(kb, query, limit=limit)
    results = _rerank_results(results)

    # Check pitfalls against changed files
    changed_files = _extract_changed_files(diff_text, repo_path)
    all_pitfalls: list[dict] = []
    for f in changed_files:
        if f.exists():
            all_pitfalls.extend(check_pitfalls(f, kb))

    # Format output
    lines = [f"# brief: {diff} → {len(results)} match(es)"]

    if all_pitfalls:
        lines.append("")
        for pf in all_pitfalls:
            lines.append(f"WARNING: {pf['warning']} [{pf['paper_id']}]")
        lines.append("")

    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r.score:.1f}] {r.title} — {r.path}")

    typer.echo("\n".join(lines))


def _extract_diff_concepts(diff_text: str) -> list[str]:
    """Extract meaningful terms from a git diff.

    Focuses on added lines (+ prefix), extracts identifiers,
    filters noise.
    """
    stopwords = {
        "import",
        "from",
        "def",
        "class",
        "return",
        "self",
        "none",
        "true",
        "false",
        "pass",
        "raise",
        "except",
        "try",
        "finally",
        "with",
        "yield",
        "async",
        "await",
        "print",
        "str",
        "int",
        "float",
        "list",
        "dict",
        "set",
        "bool",
        "path",
        "none",
        "type",
        "args",
        "kwargs",
    }

    terms: set[str] = set()
    for line in diff_text.split("\n"):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        # Extract words from added lines
        words = re.findall(r"[a-z][a-z0-9_]{2,}", line.lower())
        for w in words:
            if w not in stopwords and len(w) > 3:
                terms.add(w)

    return sorted(terms)


def _extract_changed_files(diff_text: str, repo_path: Path) -> list[Path]:
    """Extract file paths from diff header lines."""
    files: list[Path] = []
    for line in diff_text.split("\n"):
        if line.startswith("+++ b/"):
            rel = line[6:]
            full = repo_path / rel
            if full.suffix == ".py":
                files.append(full)
    return files


def _rerank_results(results: list) -> list:
    """Prefer papers, then codebases, then package index pages."""

    def bucket(result: object) -> tuple[int, float, str]:
        path = str(result.path)
        if path.startswith("papers/"):
            rank = 0
        elif path.startswith("codebases/"):
            rank = 1
        elif path.startswith("packages/") and (
            path.endswith("/_index.md") or path.endswith("/index.md")
        ):
            rank = 3
        elif path.startswith("packages/"):
            rank = 2
        else:
            rank = 4
        return (rank, -float(result.score), path)

    return sorted(results, key=bucket)
