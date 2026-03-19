"""Reference finder — find papers that support a claim.

Core workflow:
1. Search the local KB for matching papers
2. If KB coverage is thin, widen to OpenAlex/Exa
3. Rank by relevance
4. Return structured citations

Used by: find-refs, bib-gap, reviewer response.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Reference:
    """A paper found to support a claim."""

    title: str
    doi: str
    year: int | None
    topic: str
    path: str
    """KB path (empty if external-only)."""
    abstract: str
    relevance: float
    """0-1 relevance score."""
    source: str
    """'kb' or 'external'."""


@dataclass
class ClaimResult:
    """References found for a single claim."""

    claim: str
    references: list[Reference] = field(default_factory=list)
    kb_count: int = 0
    external_count: int = 0


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

# Patterns that indicate a factual claim needing a citation
_CLAIM_PATTERNS = [
    # Statements with hedging language that imply citation needed
    r"(?:studies? (?:have )?show(?:s|ed|n)?|"
    r"research (?:has )?(?:demonstrated|indicated|suggested|found)|"
    r"it (?:has been|is) (?:shown|demonstrated|established|reported)|"
    r"according to (?:the )?literature|"
    r"(?:previous|recent|several|many) (?:studies|works?|authors?)|"
    r"(?:is|are|was|were) (?:widely |commonly )?(?:used|applied|adopted)|"
    r"has been (?:widely |extensively )?(?:used|applied|studied))",
]

_CLAIM_RE = re.compile("|".join(_CLAIM_PATTERNS), re.IGNORECASE)


def extract_claims(text: str) -> list[str]:
    """Extract sentences that look like factual claims needing citations.

    Finds sentences containing claim-indicating phrases that don't
    already have a citation nearby (no [N], (Author, Year), etc.).

    Args:
        text: Markdown text (paper draft).

    Returns:
        List of claim sentences.
    """
    # Split into sentences (rough but sufficient)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    claims: list[str] = []

    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 20:
            continue

        # Skip if already has a citation
        if re.search(r"\[\d+\]|\([A-Z][a-z]+.*?\d{4}\)", sent):
            continue

        # Check for claim patterns
        if _CLAIM_RE.search(sent):
            claims.append(sent)

    return claims


# ---------------------------------------------------------------------------
# Reference search
# ---------------------------------------------------------------------------


def find_references(
    claim: str,
    kb_path: Path,
    *,
    min_kb_results: int = 3,
    max_results: int = 5,
    search_external: bool = True,
) -> ClaimResult:
    """Find papers that support a claim.

    Searches the KB first. If fewer than ``min_kb_results`` are found
    and ``search_external`` is True, widens to OpenAlex.

    Args:
        claim: The factual claim to find references for.
        kb_path: Knowledge base root.
        min_kb_results: Minimum KB results before searching externally.
        max_results: Total maximum results to return.
        search_external: Whether to search external APIs.

    Returns:
        ClaimResult with ranked references.
    """
    result = ClaimResult(claim=claim)

    # Step 1: Search KB
    kb_refs = _search_kb(claim, kb_path, limit=max_results)
    result.references.extend(kb_refs)
    result.kb_count = len(kb_refs)

    # Step 2: If KB coverage is thin, search externally
    if len(kb_refs) < min_kb_results and search_external:
        remaining = max_results - len(kb_refs)
        if remaining > 0:
            ext_refs = _search_external(claim, kb_path, limit=remaining)
            result.references.extend(ext_refs)
            result.external_count = len(ext_refs)

    # Sort by relevance
    result.references.sort(key=lambda r: -r.relevance)
    return result


def _search_kb(claim: str, kb_path: Path, limit: int) -> list[Reference]:
    """Search the local KB for papers matching a claim."""
    from papermind.query.dispatch import run_search

    results = run_search(kb_path, claim, limit=limit)
    refs: list[Reference] = []

    # Enrich with catalog metadata
    from papermind.catalog.index import CatalogIndex

    catalog = CatalogIndex(kb_path)
    path_to_entry = {e.path: e for e in catalog.entries}

    for r in results:
        entry = path_to_entry.get(r.path)
        if entry:
            # Read abstract from frontmatter if available
            abstract = ""
            full_path = kb_path / entry.path
            if full_path.exists():
                try:
                    import frontmatter as fm_lib

                    post = fm_lib.load(full_path)
                    abstract = post.metadata.get("abstract", "") or ""
                except Exception:
                    pass

            refs.append(
                Reference(
                    title=entry.title,
                    doi=entry.doi,
                    year=None,  # may not be in catalog
                    topic=entry.topic,
                    path=entry.path,
                    abstract=abstract[:300],
                    relevance=min(r.score, 1.0),
                    source="kb",
                )
            )

    return refs


def _search_external(claim: str, kb_path: Path, limit: int) -> list[Reference]:
    """Search external APIs (OpenAlex/Exa) for papers matching a claim."""
    import asyncio

    try:
        from papermind.config import load_config
        from papermind.discovery.orchestrator import discover_papers
        from papermind.discovery.providers import build_providers

        config = load_config(kb_path)
        providers = build_providers("all", config)
        if not providers:
            return []

        results = asyncio.run(discover_papers(claim, providers, limit=limit))

        refs: list[Reference] = []
        for r in results:
            refs.append(
                Reference(
                    title=r.title or "",
                    doi=r.doi or "",
                    year=r.year,
                    topic="",
                    path="",
                    abstract=(r.abstract or "")[:300],
                    relevance=0.5,  # external results get base relevance
                    source="external",
                )
            )
        return refs
    except Exception as exc:
        logger.warning("External search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Bibliography gap analysis
# ---------------------------------------------------------------------------


def analyze_bibliography_gaps(
    draft_path: Path,
    kb_path: Path,
    *,
    search_external: bool = True,
) -> list[ClaimResult]:
    """Analyze a paper draft for claims missing citations.

    Extracts claims, searches for references, returns results
    for claims that have supporting papers.

    Args:
        draft_path: Path to the markdown draft.
        kb_path: Knowledge base root.
        search_external: Whether to widen to external APIs.

    Returns:
        List of ClaimResult for each uncited claim.
    """
    text = draft_path.read_text(encoding="utf-8", errors="replace")
    claims = extract_claims(text)

    results: list[ClaimResult] = []
    for claim in claims:
        cr = find_references(claim, kb_path, search_external=search_external)
        if cr.references:
            results.append(cr)

    return results


# ---------------------------------------------------------------------------
# Reviewer response
# ---------------------------------------------------------------------------


def find_evidence_for_comment(
    comment: str,
    kb_path: Path,
    *,
    search_external: bool = True,
) -> ClaimResult:
    """Find evidence to address a reviewer comment.

    Searches KB and external APIs for papers relevant to the
    reviewer's concern.

    Args:
        comment: The reviewer's comment or question.
        kb_path: Knowledge base root.
        search_external: Whether to widen search.

    Returns:
        ClaimResult with supporting evidence.
    """
    return find_references(
        comment,
        kb_path,
        min_kb_results=2,
        max_results=8,
        search_external=search_external,
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_claim_result(result: ClaimResult) -> str:
    """Format a single claim result as markdown."""
    lines = [f"**Claim:** {result.claim}\n"]

    if not result.references:
        lines.append("*No references found.*\n")
        return "\n".join(lines)

    for i, ref in enumerate(result.references, 1):
        src = "[KB]" if ref.source == "kb" else "[EXT]"
        doi_str = f" doi:{ref.doi}" if ref.doi else ""
        year_str = f" ({ref.year})" if ref.year else ""
        lines.append(
            f"{i}. {src} **{ref.title}**{year_str}{doi_str}\n   {ref.abstract[:150]}..."
            if len(ref.abstract) > 150
            else f"{i}. {src} **{ref.title}**{year_str}{doi_str}"
        )
        if ref.abstract and len(ref.abstract) <= 150:
            lines.append(f"   {ref.abstract}")

    lines.append(
        f"\n*{result.kb_count} from KB, {result.external_count} from external APIs*"
    )
    return "\n".join(lines)


def format_gap_analysis(results: list[ClaimResult]) -> str:
    """Format bibliography gap analysis as markdown."""
    if not results:
        return "No uncited claims found — bibliography looks complete."

    lines = [
        "## Bibliography Gap Analysis\n",
        f"Found **{len(results)}** claim(s) that may need citations.\n",
    ]

    for i, cr in enumerate(results, 1):
        lines.append(f"### Claim {i}\n")
        lines.append(format_claim_result(cr))
        lines.append("")

    return "\n".join(lines)
