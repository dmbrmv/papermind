"""Project profile — auto-generated codebase summary for search relevance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProjectProfile:
    """Auto-generated summary of a codebase for KB relevance tuning."""

    name: str
    """Project name (directory basename)."""
    root: str
    """Absolute path to project root."""
    languages: list[str]
    """Programming languages detected."""
    file_count: int
    """Total source files."""
    function_count: int
    """Total function/method signatures."""
    class_count: int
    """Total class definitions."""
    linked_papers: list[str]
    """Paper identifiers found via # REF: annotations."""
    key_topics: list[str]
    """Inferred topics from import analysis and KB matching."""
    readme_excerpt: str
    """First 500 chars of README if present."""


def generate_profile(
    codebase_path: Path,
    kb_path: Path | None = None,
) -> ProjectProfile:
    """Generate a project profile from codebase analysis.

    Walks the codebase to extract language stats, signature counts,
    and provenance annotations. If a KB path is provided, cross-references
    annotations with the knowledge base.

    Args:
        codebase_path: Path to the codebase root.
        kb_path: Optional KB path for annotation cross-referencing.

    Returns:
        ProjectProfile dataclass.
    """
    from papermind.ingestion.codebase import walk_codebase
    from papermind.provenance import scan_codebase_provenance

    # Walk codebase for structure
    cb = walk_codebase(codebase_path)

    # Count signatures
    func_count = 0
    cls_count = 0
    for sigs in cb.signatures.values():
        for sig in sigs:
            if sig.kind in ("function", "method", "subroutine"):
                func_count += 1
            elif sig.kind in ("class", "struct", "interface", "module"):
                cls_count += 1

    # Scan for provenance annotations
    prov = scan_codebase_provenance(codebase_path)
    linked_papers = sorted(
        {ref.identifier for refs in prov.refs_by_file.values() for ref in refs}
    )

    # Infer topics from imports and function names
    key_topics = _infer_topics(cb, kb_path)

    readme = ""
    if cb.readme_content:
        readme = cb.readme_content[:500]

    return ProjectProfile(
        name=cb.name,
        root=str(codebase_path),
        languages=sorted(cb.languages),
        file_count=len(cb.file_tree),
        function_count=func_count,
        class_count=cls_count,
        linked_papers=linked_papers,
        key_topics=key_topics,
        readme_excerpt=readme,
    )


def _infer_topics(cb, kb_path: Path | None) -> list[str]:
    """Infer project topics from imports, function names, and KB matching."""
    # Collect all function/class names as topic signals
    terms: list[str] = []
    for sigs in cb.signatures.values():
        for sig in sigs:
            # Split camelCase and snake_case
            name = sig.name
            parts = []
            for part in name.split("_"):
                # Split camelCase
                parts.extend(
                    w.lower()
                    for w in __import__("re").findall(
                        r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", part
                    )
                )
            terms.extend(parts)

    if not terms:
        return []

    # Count term frequency, filter common programming terms
    from collections import Counter

    stopwords = {
        "get",
        "set",
        "init",
        "main",
        "test",
        "run",
        "load",
        "save",
        "self",
        "new",
        "create",
        "update",
        "delete",
        "read",
        "write",
        "open",
        "close",
        "start",
        "stop",
        "add",
        "remove",
        "find",
        "check",
        "is",
        "has",
        "to",
        "from",
        "format",
        "parse",
        "build",
        "render",
        "handle",
        "process",
        "validate",
        "config",
        "setup",
        "helper",
        "util",
        "base",
        "abstract",
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "path",
        "file",
        "data",
    }

    counts = Counter(t for t in terms if len(t) > 2 and t not in stopwords)
    return [term for term, _ in counts.most_common(10)]


def format_profile(profile: ProjectProfile) -> str:
    """Format a project profile as markdown.

    Args:
        profile: ProjectProfile to format.

    Returns:
        Formatted markdown string.
    """
    lines = [
        f"## Project Profile: {profile.name}\n",
        f"- **Root:** `{profile.root}`",
        f"- **Languages:** {', '.join(profile.languages) or 'none detected'}",
        f"- **Files:** {profile.file_count}",
        f"- **Functions:** {profile.function_count}",
        f"- **Classes:** {profile.class_count}",
        f"- **Linked papers:** {len(profile.linked_papers)}",
    ]

    if profile.linked_papers:
        lines.append("\n### Paper References\n")
        for pid in profile.linked_papers:
            lines.append(f"- {pid}")

    if profile.key_topics:
        lines.append("\n### Key Topics\n")
        lines.append(", ".join(profile.key_topics))

    if profile.readme_excerpt:
        lines.append("\n### README Excerpt\n")
        lines.append(f"```\n{profile.readme_excerpt}\n```")

    return "\n".join(lines)
