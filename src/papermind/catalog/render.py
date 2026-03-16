"""Render catalog.json entries into catalog.md."""

from __future__ import annotations

from collections import defaultdict

from papermind.catalog.index import CatalogEntry


def render_catalog_md(entries: list[CatalogEntry]) -> str:
    """Render entries into human-readable markdown.

    Args:
        entries: List of catalog entries.

    Returns:
        Markdown string for catalog.md.
    """
    papers = [e for e in entries if e.type == "paper"]
    packages = [e for e in entries if e.type == "package"]
    codebases = [e for e in entries if e.type == "codebase"]

    lines = [
        "# PaperMind Knowledge Base",
        "",
        f"> {len(papers)} papers | {len(packages)} packages"
        f" | {len(codebases)} codebases",
        "",
    ]

    # Papers grouped by topic
    if papers:
        lines.append("## Papers")
        lines.append("")
        by_topic: dict[str, list[CatalogEntry]] = defaultdict(list)
        for p in papers:
            by_topic[p.topic or "uncategorized"].append(p)
        for topic in sorted(by_topic):
            group = by_topic[topic]
            label = topic.replace("-", " ").replace("_", " ").title().replace(" ", "-")
            lines.append(f"### {label} ({len(group)})")
            lines.append("")
            for p in sorted(group, key=lambda x: x.added, reverse=True):
                lines.append(f"- [{p.title}]({p.path}) — {p.added}")
            lines.append("")

    # Packages
    if packages:
        lines.append("## Packages")
        lines.append("")
        for p in sorted(packages, key=lambda x: x.title or x.id):
            file_count = len(p.files) if p.files else 0
            lines.append(f"- [{p.title or p.id}]({p.path}) — {file_count} files")
        lines.append("")

    # Codebases
    if codebases:
        lines.append("## Codebases")
        lines.append("")
        for c in sorted(codebases, key=lambda x: x.title or x.id):
            file_count = len(c.files) if c.files else 0
            lines.append(f"- [{c.title or c.id}]({c.path}) — {file_count} files")
        lines.append("")

    if not entries:
        lines.append("_Empty knowledge base. Run `papermind ingest` to add content._")
        lines.append("")

    return "\n".join(lines)
