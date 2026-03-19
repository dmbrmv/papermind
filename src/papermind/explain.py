"""Concept / parameter glossary — fast lookup with KB search fallback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExplainResult:
    """Structured explanation of a concept or parameter."""

    name: str
    """Full name of the concept."""
    definition: str
    """One-paragraph definition."""
    range: list | None
    """Typical value range [min, max], or None if not a numeric parameter."""
    unit: str | None
    """Unit of measurement, or None."""
    related: list[str]
    """Related concepts / aliases."""
    ref: str
    """Key reference (paper, textbook, DOI)."""
    source: str
    """Where the result came from: 'glossary' or 'kb_search'."""


def _load_glossary() -> dict:
    """Load the curated glossary YAML."""
    import yaml

    glossary_path = Path(__file__).parent / "glossary.yaml"
    if not glossary_path.exists():
        return {}
    with open(glossary_path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _glossary_lookup(concept: str) -> ExplainResult | None:
    """Try exact or case-insensitive match in the glossary."""
    glossary = _load_glossary()
    if not glossary:
        return None

    # Exact match
    if concept in glossary:
        return _entry_to_result(glossary[concept])

    # Case-insensitive match
    lower = concept.lower()
    for key, entry in glossary.items():
        if key.lower() == lower:
            return _entry_to_result(entry)
        # Also check the full name field
        if entry.get("name", "").lower() == lower:
            return _entry_to_result(entry)

    # Alias match — check related terms
    for _key, entry in glossary.items():
        related = [r.lower() for r in entry.get("related", [])]
        if lower in related:
            return _entry_to_result(entry)

    return None


def _entry_to_result(entry: dict) -> ExplainResult:
    """Convert a glossary YAML entry to an ExplainResult."""
    return ExplainResult(
        name=entry.get("name", ""),
        definition=entry.get("definition", "").strip(),
        range=entry.get("range"),
        unit=entry.get("unit"),
        related=entry.get("related", []),
        ref=entry.get("ref", ""),
        source="glossary",
    )


def _kb_search_explain(concept: str, kb_path: Path) -> ExplainResult | None:
    """Fall back to KB search to build an explanation."""
    from papermind.query.fallback import fallback_search
    from papermind.query.qmd import is_qmd_available, qmd_search

    if is_qmd_available():
        results = qmd_search(kb_path, concept, limit=3)
    else:
        results = fallback_search(kb_path, concept, limit=3)

    if not results:
        return None

    top = results[0]

    # Build a minimal explanation from the best search result
    snippet = top.snippet[:500] if top.snippet else ""
    ref_parts = [top.title]
    if top.path:
        ref_parts.append(f"({top.path})")

    return ExplainResult(
        name=concept,
        definition=snippet if snippet else f"Found in: {top.title}",
        range=None,
        unit=None,
        related=[],
        ref=" ".join(ref_parts),
        source="kb_search",
    )


def explain(concept: str, kb_path: Path | None = None) -> ExplainResult | None:
    """Look up a concept — glossary first, KB search fallback.

    Args:
        concept: Parameter name or concept to explain (e.g. "CN2", "baseflow").
        kb_path: Knowledge base root. Required for KB search fallback.

    Returns:
        ExplainResult if found, None if not.
    """
    result = _glossary_lookup(concept)
    if result:
        return result

    if kb_path and kb_path.is_dir():
        return _kb_search_explain(concept, kb_path)

    return None


def format_explain(result: ExplainResult) -> str:
    """Format an ExplainResult as readable text.

    Args:
        result: The explain result to format.

    Returns:
        Formatted string.
    """
    lines = [f"## {result.name}"]
    lines.append("")
    lines.append(result.definition)

    if result.range is not None:
        lo, hi = result.range
        unit = f" {result.unit}" if result.unit else ""
        lines.append(f"\n**Range:** {lo} – {hi}{unit}")
    elif result.unit:
        lines.append(f"\n**Unit:** {result.unit}")

    if result.related:
        lines.append(f"\n**Related:** {', '.join(result.related)}")

    if result.ref:
        lines.append(f"\n**Reference:** {result.ref}")

    lines.append(f"\n*Source: {result.source}*")
    return "\n".join(lines)
