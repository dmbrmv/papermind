"""Search dispatch — shared by MCP handlers and REST API routes."""

from __future__ import annotations

from pathlib import Path


def run_search(
    kb_path: Path,
    q: str,
    *,
    scope: str = "",
    topic: str = "",
    year_from: int | None = None,
    limit: int = 10,
) -> list:
    """Run search using qmd (semantic) or grep fallback.

    Args:
        kb_path: Knowledge base root.
        q: Search query.
        scope: Filter by content type (papers/packages/codebases).
        topic: Filter by topic.
        year_from: Papers from this year onward.
        limit: Maximum results.

    Returns:
        List of SearchResult objects.
    """
    from papermind.query.fallback import fallback_search
    from papermind.query.qmd import is_qmd_available, qmd_search

    if is_qmd_available():
        return qmd_search(kb_path, q, scope=scope or "", limit=limit)
    return fallback_search(
        kb_path,
        q,
        scope=scope or None,
        topic=topic or None,
        year_from=year_from,
        limit=limit,
    )
