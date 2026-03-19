"""Auto-cite — find references with automatic discovery and ingestion.

The NotebookLM-style workflow: search KB → if gaps → discover externally →
download + ingest the best papers → return all references. The KB grows
organically from actual research questions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AutoCiteResult:
    """Result of an auto-cite operation."""

    claim: str
    kb_refs: list[dict] = field(default_factory=list)
    """References found in KB."""
    newly_ingested: list[dict] = field(default_factory=list)
    """Papers discovered, downloaded, and ingested this run."""
    external_only: list[dict] = field(default_factory=list)
    """External papers found but not ingested (no PDF URL)."""
    total: int = 0


def auto_cite(
    claim: str,
    kb_path: Path,
    *,
    topic: str = "uncategorized",
    min_kb_results: int = 3,
    max_results: int = 5,
    max_ingest: int = 3,
) -> AutoCiteResult:
    """Find references, auto-ingesting external papers when KB is thin.

    1. Search KB for papers matching the claim
    2. If fewer than ``min_kb_results``, search OpenAlex/Exa
    3. For external results with PDF URLs: download → OCR → ingest
    4. Return all references (KB + freshly ingested)

    Args:
        claim: Factual claim to find references for.
        kb_path: Knowledge base root.
        topic: Topic for newly ingested papers.
        min_kb_results: Trigger external search if KB has fewer.
        max_results: Total maximum references to return.
        max_ingest: Maximum papers to auto-ingest per call.

    Returns:
        AutoCiteResult with KB refs + newly ingested papers.
    """
    from papermind.query.dispatch import run_search

    result = AutoCiteResult(claim=claim)

    # Step 1: Search KB
    kb_results = run_search(kb_path, claim, limit=max_results)

    # Enrich KB results with catalog metadata
    from papermind.catalog.index import CatalogIndex

    catalog = CatalogIndex(kb_path)
    path_to_entry = {e.path: e for e in catalog.entries}

    for r in kb_results:
        entry = path_to_entry.get(r.path)
        if entry:
            result.kb_refs.append(
                {
                    "title": entry.title,
                    "doi": entry.doi,
                    "topic": entry.topic,
                    "path": entry.path,
                    "score": r.score,
                    "source": "kb",
                }
            )

    # Step 2: If KB coverage is thin, discover + ingest
    if len(result.kb_refs) < min_kb_results:
        logger.info(
            "KB has %d results (need %d), searching externally...",
            len(result.kb_refs),
            min_kb_results,
        )
        _discover_and_ingest(claim, kb_path, topic, result, max_ingest=max_ingest)

    result.total = (
        len(result.kb_refs) + len(result.newly_ingested) + len(result.external_only)
    )
    return result


def _discover_and_ingest(
    claim: str,
    kb_path: Path,
    topic: str,
    result: AutoCiteResult,
    *,
    max_ingest: int = 3,
) -> None:
    """Discover external papers and auto-ingest those with PDFs."""
    try:
        from papermind.config import load_config
        from papermind.discovery.orchestrator import discover_papers
        from papermind.discovery.providers import build_providers

        config = load_config(kb_path)
        providers = build_providers("all", config)
        if not providers:
            logger.warning("No external providers configured")
            return

        discoveries = asyncio.run(
            discover_papers(claim, providers, limit=max_ingest * 3)
        )

        if not discoveries:
            return

        # Dedup against existing KB
        from papermind.catalog.index import CatalogIndex

        catalog = CatalogIndex(kb_path)
        existing_dois = {e.doi for e in catalog.entries if e.doi}

        ingested = 0
        for paper in discoveries:
            if paper.doi and paper.doi in existing_dois:
                continue

            ref_info = {
                "title": paper.title or "",
                "doi": paper.doi or "",
                "year": paper.year,
                "abstract": (paper.abstract or "")[:300],
            }

            if paper.pdf_url and ingested < max_ingest:
                # Try to download and ingest
                entry = _download_and_ingest(paper, kb_path, topic, config)
                if entry:
                    ref_info["path"] = entry.path
                    ref_info["source"] = "auto_ingested"
                    result.newly_ingested.append(ref_info)
                    ingested += 1
                    if paper.doi:
                        existing_dois.add(paper.doi)
                    continue

            ref_info["source"] = "external"
            result.external_only.append(ref_info)

    except Exception as exc:
        logger.warning("External discovery failed: %s", exc)


def _download_and_ingest(paper, kb_path: Path, topic: str, config) -> object | None:
    """Download a paper PDF and ingest it into the KB.

    Returns:
        CatalogEntry if successful, None if failed.
    """
    import asyncio

    try:
        from papermind.discovery.downloader import download_paper

        pdf_dir = kb_path / "pdfs"
        pdf_dir.mkdir(exist_ok=True)

        pdf_path = asyncio.run(download_paper(paper, pdf_dir))
        if not pdf_path:
            return None

        from papermind.ingestion.paper import ingest_paper

        entry = ingest_paper(
            pdf_path,
            topic,
            kb_path,
            config,
            no_reindex=True,
            abstract=paper.abstract or "",
            cites=paper.cites or None,
            cited_by=paper.cited_by or None,
        )

        if entry:
            logger.info("Auto-ingested: %s", entry.title[:60])
        return entry

    except Exception as exc:
        logger.debug("Failed to auto-ingest %s: %s", paper.title, exc)
        return None


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_auto_cite(result: AutoCiteResult) -> str:
    """Format auto-cite result as markdown."""
    lines = [f"**Claim:** {result.claim}\n"]

    if result.kb_refs:
        lines.append(f"### From KB ({len(result.kb_refs)})\n")
        for i, r in enumerate(result.kb_refs, 1):
            doi = f" doi:{r['doi']}" if r.get("doi") else ""
            lines.append(f"{i}. **{r['title']}**{doi}")

    if result.newly_ingested:
        lines.append(f"\n### Auto-ingested ({len(result.newly_ingested)})\n")
        for i, r in enumerate(result.newly_ingested, 1):
            doi = f" doi:{r['doi']}" if r.get("doi") else ""
            year = f" ({r['year']})" if r.get("year") else ""
            lines.append(f"{i}. **{r['title']}**{year}{doi}")
            lines.append("   *Downloaded and added to KB*")

    if result.external_only:
        lines.append(f"\n### External only ({len(result.external_only)})\n")
        for i, r in enumerate(result.external_only, 1):
            doi = f" doi:{r['doi']}" if r.get("doi") else ""
            lines.append(f"{i}. {r['title']}{doi}")

    lines.append(f"\n*Total: {result.total} references*")
    return "\n".join(lines)
