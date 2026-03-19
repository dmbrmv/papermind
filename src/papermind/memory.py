"""Agent memory integration — parse and resolve kb: references in markdown.

Supports ``kb:paper-id`` or ``kb:doi:10.xxx/yyy`` references in any markdown
file (MEMORY.md, CLAUDE.md, notes, etc.).  Resolves them to paper titles,
paths, and metadata from the knowledge base.

Reference format::

    See kb:paper-green-ampt-1911 for infiltration details.
    Based on kb:doi:10.1016/j.jhydrol.2012.03.001 equation 4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class KBRef:
    """A kb: reference found in a markdown file."""

    raw: str
    """Raw reference text (e.g. 'kb:paper-green-ampt-1911')."""
    identifier: str
    """Resolved identifier (paper ID or DOI)."""
    identifier_type: str
    """'paper_id' or 'doi'."""
    line: int
    """Line number (1-based)."""


@dataclass
class ResolvedRef:
    """A kb: reference resolved against the knowledge base."""

    ref: KBRef
    """The original reference."""
    found: bool
    """Whether the reference was found in the KB."""
    title: str
    """Paper title (empty if not found)."""
    path: str
    """Relative path in KB (empty if not found)."""
    topic: str
    """Paper topic (empty if not found)."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_KB_REF_PATTERN = re.compile(
    r"kb:(doi:)?(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+|paper-[a-z0-9][-a-z0-9]*)"
)


def extract_kb_refs(text: str) -> list[KBRef]:
    """Extract all kb: references from markdown text.

    Args:
        text: Markdown file content.

    Returns:
        List of KBRef objects.
    """
    refs: list[KBRef] = []
    for line_num, line in enumerate(text.splitlines(), 1):
        for m in _KB_REF_PATTERN.finditer(line):
            identifier = m.group(2).rstrip(".,;)")
            has_doi_prefix = m.group(1) is not None
            id_type = (
                "doi" if has_doi_prefix or identifier.startswith("10.") else "paper_id"
            )

            refs.append(
                KBRef(
                    raw=m.group(0),
                    identifier=identifier,
                    identifier_type=id_type,
                    line=line_num,
                )
            )
    return refs


def extract_kb_refs_from_file(path: Path) -> list[KBRef]:
    """Extract kb: references from a markdown file.

    Args:
        path: Path to the markdown file.

    Returns:
        List of KBRef objects.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return extract_kb_refs(text)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_refs(
    refs: list[KBRef],
    kb_path: Path,
) -> list[ResolvedRef]:
    """Resolve kb: references against the knowledge base.

    Args:
        refs: List of KBRef to resolve.
        kb_path: Knowledge base root.

    Returns:
        List of ResolvedRef with resolution status.
    """
    from papermind.catalog.index import CatalogIndex

    catalog = CatalogIndex(kb_path)
    results: list[ResolvedRef] = []

    for ref in refs:
        entry = None

        if ref.identifier_type == "doi":
            # Search by DOI
            for e in catalog.entries:
                if e.doi == ref.identifier:
                    entry = e
                    break
        else:
            # Search by paper ID
            entry = catalog.get(ref.identifier)

        if entry:
            results.append(
                ResolvedRef(
                    ref=ref,
                    found=True,
                    title=entry.title or "",
                    path=entry.path or "",
                    topic=entry.topic or "",
                )
            )
        else:
            results.append(
                ResolvedRef(
                    ref=ref,
                    found=False,
                    title="",
                    path="",
                    topic="",
                )
            )

    return results


def validate_refs_in_file(
    path: Path,
    kb_path: Path,
) -> tuple[list[ResolvedRef], list[ResolvedRef]]:
    """Validate all kb: references in a file against the KB.

    Args:
        path: Path to the markdown file.
        kb_path: Knowledge base root.

    Returns:
        Tuple of (valid_refs, broken_refs).
    """
    refs = extract_kb_refs_from_file(path)
    if not refs:
        return [], []

    resolved = resolve_refs(refs, kb_path)
    valid = [r for r in resolved if r.found]
    broken = [r for r in resolved if not r.found]
    return valid, broken


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_resolved_refs(resolved: list[ResolvedRef]) -> str:
    """Format resolved references as markdown.

    Args:
        resolved: List of ResolvedRef to format.

    Returns:
        Formatted markdown string.
    """
    if not resolved:
        return "No kb: references found."

    lines = [f"**{len(resolved)} reference(s) found:**\n"]
    for r in resolved:
        status = "[found]" if r.found else "[NOT FOUND]"
        if r.found:
            lines.append(
                f"- L{r.ref.line}: `{r.ref.raw}` {status}\n"
                f"  **{r.title}** ({r.topic}) — `{r.path}`"
            )
        else:
            lines.append(f"- L{r.ref.line}: `{r.ref.raw}` {status}")

    return "\n".join(lines)


def format_validation(
    valid: list[ResolvedRef],
    broken: list[ResolvedRef],
) -> str:
    """Format validation results.

    Args:
        valid: Successfully resolved references.
        broken: References not found in KB.

    Returns:
        Formatted markdown string.
    """
    total = len(valid) + len(broken)
    if total == 0:
        return "No kb: references found in file."

    lines = [f"**{total} reference(s) checked:**\n"]
    lines.append(f"- Valid: {len(valid)}")
    lines.append(f"- Broken: {len(broken)}")

    if broken:
        lines.append("\n### Broken References\n")
        for r in broken:
            lines.append(f"- L{r.ref.line}: `{r.ref.raw}` — not in KB")

    return "\n".join(lines)
