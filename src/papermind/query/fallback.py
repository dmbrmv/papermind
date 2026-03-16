"""Grep-based fallback search for the PaperMind knowledge base.

No external dependencies required — walks .md files, counts term
occurrences, ranks by match density, and extracts a snippet around
the first match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SearchResult:
    """A single search result from the fallback search."""

    path: str
    """Path relative to the KB root."""
    title: str
    """Title extracted from frontmatter or derived from filename."""
    snippet: str
    """~200 chars of context around the first match."""
    score: float
    """Relevance score: matches per KB of content (higher is better)."""


def _extract_frontmatter_field(text: str, field: str) -> str:
    """Return a frontmatter field value or empty string.

    Args:
        text: Full file content.
        field: YAML field name to extract.

    Returns:
        Field value (unquoted) or empty string.
    """
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            m = re.match(rf"^{re.escape(field)}\s*:\s*(.+)$", line.strip())
            if m:
                return m.group(1).strip().strip("\"'")
    return ""


def _extract_frontmatter_title(text: str, filepath: Path) -> str:
    """Return the frontmatter title or a humanised filename fallback.

    Args:
        text: Full file content.
        filepath: Path to the file (used as fallback).

    Returns:
        Title string.
    """
    title = _extract_frontmatter_field(text, "title")
    if title:
        return title
    return filepath.stem.replace("-", " ").replace("_", " ").title()


def _build_snippet(text: str, pattern: re.Pattern[str], context: int = 200) -> str:
    """Extract ~context chars around the first regex match.

    Args:
        text: Full file content.
        pattern: Compiled regex to search for.
        context: Number of characters of context on each side of the match.

    Returns:
        Snippet string with ellipsis markers where text was trimmed.
    """
    m = pattern.search(text)
    if not m:
        return ""
    start = max(0, m.start() - context // 2)
    end = min(len(text), m.end() + context // 2)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def _load_aliases() -> dict[str, list[str]]:
    """Load search aliases from bundled YAML file."""
    import yaml

    aliases_path = Path(__file__).parent.parent / "aliases.yaml"
    if not aliases_path.exists():
        return {}
    try:
        with open(aliases_path) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _expand_aliases(terms: list[str]) -> list[str]:
    """Expand search terms using aliases."""
    aliases = _load_aliases()
    if not aliases:
        return terms

    expanded: set[str] = set(terms)
    for term in terms:
        t = term.lower()
        # Check if term is a key
        if t in aliases:
            expanded.update(aliases[t])
        # Check if term is a value
        for key, values in aliases.items():
            if t in values:
                expanded.add(key)
                expanded.update(values)
    return list(expanded)


def fallback_search(
    kb_root: Path,
    query: str,
    *,
    scope: str | None = None,
    topic: str | None = None,
    year_from: int | None = None,
    limit: int = 50,
) -> list[SearchResult]:
    """Search the KB by walking .md files and counting query-term occurrences.

    Args:
        kb_root: Root directory of the PaperMind knowledge base.
        query: Space-separated search terms (case-insensitive).
        scope: Restrict to a top-level subdirectory (e.g. "papers",
            "codebases", "packages").
        topic: Further restrict to a second-level subdirectory within scope.
        limit: Maximum number of results to return (ranked by score).

    Returns:
        List of :class:`SearchResult` sorted by descending relevance.
    """
    terms = [t.strip() for t in query.split() if t.strip()]
    if not terms:
        return []

    # Expand terms using aliases
    terms = _expand_aliases(terms)

    # Build a pattern that matches any term (case-insensitive)
    term_pattern = re.compile(
        "|".join(re.escape(t) for t in terms),
        re.IGNORECASE,
    )

    # Resolve the search root
    search_root = kb_root
    if scope:
        search_root = kb_root / scope
        if topic:
            search_root = search_root / topic
    elif topic:
        # topic without scope: search everywhere but filter by subdir name
        search_root = kb_root

    results: list[SearchResult] = []

    for md_file in sorted(search_root.rglob("*.md")):
        if not md_file.is_file():
            continue

        text = md_file.read_text(encoding="utf-8", errors="replace")

        # Year filter: skip papers older than year_from
        if year_from:
            year_str = _extract_frontmatter_field(text, "year")
            if year_str:
                try:
                    if int(year_str) < year_from:
                        continue
                except ValueError:
                    pass

        matches = term_pattern.findall(text)
        if not matches:
            continue

        size_kb = max(len(text) / 1024.0, 0.1)  # avoid div-by-zero on tiny files
        score = len(matches) / size_kb

        title = _extract_frontmatter_title(text, md_file)
        snippet = _build_snippet(text, term_pattern)
        abstract = _extract_frontmatter_field(text, "abstract")
        if abstract:
            snippet = f"[Abstract] {abstract[:200]} | {snippet}"
        rel_path = str(md_file.relative_to(kb_root))

        results.append(
            SearchResult(
                path=rel_path,
                title=title,
                snippet=snippet,
                score=score,
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]
