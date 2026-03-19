"""Code-to-paper provenance — parse # REF: annotations and scan codebases.

Annotations link source code to scientific papers. Format:

    # REF: doi:10.1029/2023WR035123 eq.4.2
    # REF: paper-green-ampt-1911 §methods
    ! REF: doi:10.5194/hess-25-2019-2021          (Fortran)
    // REF: doi:10.1016/j.jhydrol.2012.03.001      (C/C++/JS/TS)

Identifiers:
    doi:10.XXXX/...     — DOI reference
    paper-xxx-yyyy      — PaperMind paper ID

Location specifiers (optional):
    eq.N or eq.N.M      — equation number
    §section             — section name
    table.N              — table number
    fig.N                — figure number
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class CodeRef:
    """A single code-to-paper reference found in source code."""

    file: str
    """Relative path to the source file."""
    line: int
    """Line number (1-based)."""
    identifier: str
    """DOI (10.xxx/yyy) or paper ID (paper-xxx)."""
    identifier_type: str
    """'doi' or 'paper_id'."""
    location: str
    """Optional location within the paper (eq.4.2, §methods, etc.)."""
    raw: str
    """The full raw annotation text."""


@dataclass
class ProvenanceSummary:
    """Summary of provenance scan across a codebase."""

    root: str
    """Codebase root path."""
    files_scanned: int
    """Total source files scanned."""
    files_with_refs: int
    """Files containing at least one # REF: annotation."""
    total_refs: int
    """Total annotations found."""
    unique_papers: int
    """Unique paper identifiers referenced."""
    refs_by_file: dict[str, list[CodeRef]] = field(default_factory=dict)
    """All refs grouped by file."""


# ---------------------------------------------------------------------------
# Annotation regex
# ---------------------------------------------------------------------------

# Comment prefix: #, !, //, or /*...*/ opening
# Then REF: keyword, then identifier + optional location
_REF_PATTERN = re.compile(
    r"""
    (?:^\s*(?:\#|!|//|/\*)\s*)     # Comment prefix (Python/shell #, Fortran !, C/JS //)
    REF:\s*                         # REF: keyword
    (?:doi:)?                       # Optional 'doi:' prefix
    (                               # Group 1: identifier
        10\.\d{4,9}/[-._;()/:A-Za-z0-9]+   # DOI pattern
        |                                    # OR
        paper-[a-z0-9][-a-z0-9]*            # Paper ID pattern
    )
    (?:\s+(.+?))?                   # Group 2: optional location (eq.4.2, §methods, etc.)
    \s*(?:\*/)?$                    # Optional closing */ and end of line
    """,
    re.VERBOSE | re.MULTILINE,
)

# Also match inline annotations: code  # REF: ...
_INLINE_REF_PATTERN = re.compile(
    r"""
    \S.*                            # Some code before the comment
    (?:\#|!|//)\s*                  # Comment prefix
    REF:\s*                         # REF: keyword
    (?:doi:)?                       # Optional 'doi:' prefix
    (                               # Group 1: identifier
        10\.\d{4,9}/[-._;()/:A-Za-z0-9]+
        |
        paper-[a-z0-9][-a-z0-9]*
    )
    (?:\s+(.+?))?                   # Group 2: optional location
    \s*$
    """,
    re.VERBOSE,
)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract_provenance(source_path: Path, root: Path | None = None) -> list[CodeRef]:
    """Extract all # REF: annotations from a single source file.

    Args:
        source_path: Absolute path to the source file.
        root: Optional codebase root for relative path computation.

    Returns:
        List of CodeRef annotations found in the file.
    """
    try:
        text = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    rel_path = str(source_path.relative_to(root)) if root else source_path.name
    refs: list[CodeRef] = []

    for line_num, line in enumerate(text.splitlines(), 1):
        # Try standalone comment first, then inline
        match = _REF_PATTERN.match(line) or _INLINE_REF_PATTERN.match(line)
        if not match:
            continue

        identifier = match.group(1).rstrip(".,;)")
        location = (match.group(2) or "").strip()

        # Determine identifier type
        if identifier.startswith("10."):
            id_type = "doi"
        else:
            id_type = "paper_id"

        refs.append(
            CodeRef(
                file=rel_path,
                line=line_num,
                identifier=identifier,
                identifier_type=id_type,
                location=location,
                raw=line.strip(),
            )
        )

    return refs


def scan_codebase_provenance(root: Path) -> ProvenanceSummary:
    """Scan an entire codebase for # REF: annotations.

    Walks the directory tree, respecting .gitignore, and extracts all
    provenance annotations from source files.

    Args:
        root: Codebase root directory.

    Returns:
        ProvenanceSummary with all refs grouped by file.
    """
    from papermind.ingestion.codebase import (
        _detect_language,
        _is_ignored,
        _load_gitignore_patterns,
    )

    gitignore_patterns = _load_gitignore_patterns(root)

    refs_by_file: dict[str, list[CodeRef]] = {}
    files_scanned = 0
    unique_ids: set[str] = set()

    for abs_path in sorted(root.rglob("*")):
        if abs_path.is_dir():
            continue

        rel = abs_path.relative_to(root)
        rel_str = str(rel)

        if _is_ignored(rel_str, gitignore_patterns):
            continue

        # Only scan source files (detected language) + markdown
        lang = _detect_language(abs_path)
        if lang is None and abs_path.suffix.lower() not in (".md", ".markdown"):
            continue

        files_scanned += 1
        file_refs = extract_provenance(abs_path, root)

        if file_refs:
            refs_by_file[rel_str] = file_refs
            for ref in file_refs:
                unique_ids.add(ref.identifier)

    total_refs = sum(len(r) for r in refs_by_file.values())

    return ProvenanceSummary(
        root=str(root),
        files_scanned=files_scanned,
        files_with_refs=len(refs_by_file),
        total_refs=total_refs,
        unique_papers=len(unique_ids),
        refs_by_file=refs_by_file,
    )


def suggest_annotations(
    source_path: Path,
    kb_path: Path,
    *,
    limit: int = 5,
) -> list[dict]:
    """Auto-propose # REF: annotations for a source file.

    Extracts concepts from the file (function names, docstrings) and
    searches the KB for matching papers. Returns suggestions that could
    be added as annotations.

    Args:
        source_path: Path to the source file.
        kb_path: Knowledge base root.
        limit: Max suggestions to return.

    Returns:
        List of dicts with 'line', 'function', 'suggestion', 'paper_title', 'paper_path'.
    """
    from papermind.watch import extract_concepts, watch_file

    # Get relevant papers via watch
    results = watch_file(source_path, kb_path, limit=limit)
    if not results:
        return []

    # Get function names with line numbers for annotation targets
    concepts = extract_concepts(source_path)
    function_names = concepts.get("functions", [])

    # Read file to find function definition lines
    try:
        lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    function_lines: list[tuple[str, int]] = []
    for i, line in enumerate(lines, 1):
        for fn_name in function_names:
            if f"def {fn_name}" in line or f"subroutine {fn_name}" in line.lower():
                function_lines.append((fn_name, i))
                break

    suggestions = []
    for result in results:
        # Build the annotation text
        # Try to extract DOI from the paper path
        doi = _extract_doi_from_path(result.path, kb_path)
        if doi:
            ref_text = f"# REF: doi:{doi}"
        else:
            ref_text = f"# REF: {result.path}"

        suggestion = {
            "paper_title": result.title,
            "paper_path": result.path,
            "annotation": ref_text,
            "target_functions": [
                {"name": fn, "line": ln} for fn, ln in function_lines[:3]
            ],
        }
        suggestions.append(suggestion)

    return suggestions


def _extract_doi_from_path(paper_path: str, kb_path: Path) -> str:
    """Try to extract DOI from a paper's frontmatter."""
    full_path = kb_path / paper_path
    if not full_path.exists():
        return ""
    try:
        import frontmatter as fm_lib

        post = fm_lib.load(full_path)
        return post.metadata.get("doi", "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_provenance(refs: list[CodeRef]) -> str:
    """Format provenance refs as readable text.

    Args:
        refs: List of CodeRef annotations.

    Returns:
        Formatted markdown string.
    """
    if not refs:
        return "No # REF: annotations found."

    lines = [f"**{len(refs)} reference(s) found:**\n"]
    for ref in refs:
        loc = f" {ref.location}" if ref.location else ""
        id_prefix = "doi:" if ref.identifier_type == "doi" else ""
        lines.append(f"- L{ref.line}: `{id_prefix}{ref.identifier}{loc}`")

    return "\n".join(lines)


def format_summary(summary: ProvenanceSummary) -> str:
    """Format a provenance scan summary as markdown.

    Args:
        summary: ProvenanceSummary to format.

    Returns:
        Formatted markdown string.
    """
    lines = [
        f"## Provenance Scan: {summary.root}\n",
        f"- **Files scanned:** {summary.files_scanned}",
        f"- **Files with refs:** {summary.files_with_refs}",
        f"- **Total annotations:** {summary.total_refs}",
        f"- **Unique papers:** {summary.unique_papers}",
    ]

    if summary.refs_by_file:
        lines.append("\n### Files with References\n")
        for file_path, refs in sorted(summary.refs_by_file.items()):
            lines.append(f"**{file_path}** ({len(refs)} ref(s))")
            for ref in refs:
                loc = f" {ref.location}" if ref.location else ""
                lines.append(f"  - L{ref.line}: {ref.identifier}{loc}")

    return "\n".join(lines)
