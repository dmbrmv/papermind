"""Parallel discovery orchestrator — runs multiple providers and deduplicates."""

from __future__ import annotations

import asyncio
import logging
import re
from difflib import SequenceMatcher

from papermind.discovery.base import PaperResult, SearchProvider

logger = logging.getLogger(__name__)


async def discover_papers(
    query: str,
    providers: list[SearchProvider],
    *,
    limit: int = 10,
    enrich_unpaywall: bool = True,
) -> list[PaperResult]:
    """Run search across all providers in parallel and deduplicate results.

    Providers are queried concurrently.  Any provider that raises an exception
    is silently skipped — its results are dropped but other providers proceed.

    After deduplication, results with a DOI but no ``pdf_url`` are enriched
    via the Unpaywall API (free, no key needed).

    Args:
        query: Free-text search query forwarded to every provider.
        providers: List of :class:`SearchProvider` instances to query.
        limit: Max results requested from each provider.
        enrich_unpaywall: If True, resolve missing pdf_urls via Unpaywall
            after deduplication. Disable for offline or testing scenarios.

    Returns:
        Deduplicated list of :class:`PaperResult` objects with pdf_urls
        enriched where possible.
    """
    tasks = [p.search(query, limit=limit) for p in providers]
    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    flat: list[PaperResult] = []
    for result in all_results:
        if isinstance(result, list):
            flat.extend(result)
        # Exception return values are silently skipped — provider already logs.

    unique = _deduplicate(flat)

    if enrich_unpaywall:
        await _enrich_pdf_urls(unique)

    return _rank_results(unique)


async def _enrich_pdf_urls(results: list[PaperResult]) -> None:
    """Resolve missing pdf_urls via Unpaywall for results that have a DOI.

    Runs all Unpaywall lookups concurrently.  Failures are silently skipped
    (the result simply keeps ``pdf_url == ""``).

    Args:
        results: Deduplicated list — modified in place.
    """
    from papermind.discovery.unpaywall import resolve_pdf_url

    candidates = [r for r in results if r.doi and not r.pdf_url]
    if not candidates:
        return

    logger.debug("Unpaywall enrichment: %d candidate(s)", len(candidates))

    resolved = await asyncio.gather(
        *(resolve_pdf_url(r.doi) for r in candidates),
        return_exceptions=True,
    )

    for paper, url in zip(candidates, resolved):
        if isinstance(url, str) and url:
            paper.pdf_url = url


def _rank_results(results: list[PaperResult]) -> list[PaperResult]:
    """Sort results by quality score (highest first).

    No results are dropped — only reordered.  This works for papers,
    packages, and codebases without special casing.

    Args:
        results: Deduplicated, enriched list of results.

    Returns:
        Same results sorted by descending quality score.
    """
    return sorted(results, key=_score_result, reverse=True)


# Domains that strongly signal academic content
_ACADEMIC_DOMAINS = frozenset(
    {
        "arxiv.org",
        "doi.org",
        "researchgate.net",
        "springer.com",
        "wiley.com",
        "sciencedirect.com",
        "nature.com",
        "pnas.org",
        "nih.gov",
        "ncbi.nlm.nih.gov",
        "jstor.org",
        "ieee.org",
        "acm.org",
        "biorxiv.org",
        "medrxiv.org",
        "ssrn.com",
        "mdpi.com",
        "frontiersin.org",
        "plos.org",
        "semanticscholar.org",
    }
)

# Domains that are noise for academic discovery
_NOISE_DOMAINS = frozenset(
    {
        "linkedin.com",
        "youtube.com",
        "twitter.com",
        "x.com",
        "facebook.com",
        "reddit.com",
        "medium.com",
        "quora.com",
        "pinterest.com",
        "instagram.com",
        "tiktok.com",
    }
)

# Simple heuristic: title contains common academic patterns
_ACADEMIC_TITLE_RE = re.compile(
    r"(?:analysis|assessment|evaluation|simulation|modeling|modelling|"
    r"review|approach|framework|method|estimation|prediction|"
    r"calibration|validation|comparison|impact|response|dynamics|"
    r"study|investigation|characterization|quantification)",
    re.IGNORECASE,
)


def _score_result(result: PaperResult) -> int:
    """Compute a quality score for a discovery result.

    Scoring signals:
        +3  has DOI
        +3  has pdf_url
        +2  title looks academic (contains common research terms)
        +1  URL on a known academic domain (arxiv, doi.org, .edu, journals)
        -3  URL on a social/noise domain (linkedin, youtube, twitter)

    Args:
        result: A single paper result.

    Returns:
        Integer score (higher is better).
    """

    score = 0

    if result.doi:
        score += 3
    if result.pdf_url:
        score += 3
    if _ACADEMIC_TITLE_RE.search(result.title):
        score += 2

    # Check URL domain signals (from pdf_url or source URL if available)
    url = result.pdf_url or ""
    if url:
        domain = _extract_domain(url)
        if domain:
            if domain in _NOISE_DOMAINS:
                score -= 3
            elif domain in _ACADEMIC_DOMAINS or domain.endswith(".edu"):
                score += 1

    return score


def _extract_domain(url: str) -> str:
    """Extract the base domain from a URL for classification.

    Args:
        url: Full URL string.

    Returns:
        Lowercase domain (e.g. ``"arxiv.org"``) or empty string.
    """
    match = re.match(r"https?://(?:www\.)?([^/]+)", url)
    if not match:
        return ""
    return match.group(1).lower()


def _deduplicate(results: list[PaperResult]) -> list[PaperResult]:
    """Deduplicate by DOI (exact) or fuzzy title + year overlap (>90%).

    When two results are considered duplicates the one already in the output
    list is kept as the *target* and any missing metadata from the *source*
    is merged into it.

    Args:
        results: Flat list of paper results, potentially with duplicates.

    Returns:
        Deduplicated list with metadata merged where possible.
    """
    seen_dois: set[str] = set()
    unique: list[PaperResult] = []

    for r in results:
        # --- DOI exact-match dedup ---
        if r.doi and r.doi in seen_dois:
            # Find the existing record and merge extra metadata in.
            for existing in unique:
                if existing.doi == r.doi:
                    _merge_into(existing, r)
                    break
            continue

        # --- Fuzzy title + year dedup ---
        is_dup = False
        for existing in unique:
            similarity = SequenceMatcher(
                None, r.title.lower(), existing.title.lower()
            ).ratio()
            if similarity > 0.9:
                # Same year, or either year is unknown → treat as duplicate.
                if r.year == existing.year or r.year is None or existing.year is None:
                    _merge_into(existing, r)
                    is_dup = True
                    break

        if not is_dup:
            if r.doi:
                seen_dois.add(r.doi)
            unique.append(r)

    return unique


def _merge_into(target: PaperResult, source: PaperResult) -> None:
    """Merge non-empty fields from *source* into *target* where *target* is empty.

    Args:
        target: The record that will be updated in place.
        source: The record whose metadata fills gaps in *target*.
    """
    if not target.doi and source.doi:
        target.doi = source.doi
    if not target.pdf_url and source.pdf_url:
        target.pdf_url = source.pdf_url
    if not target.abstract and source.abstract:
        target.abstract = source.abstract
    if not target.year and source.year:
        target.year = source.year
    if not target.authors and source.authors:
        target.authors = source.authors
    if not target.cites and source.cites:
        target.cites = source.cites
    if not target.cited_by and source.cited_by:
        target.cited_by = source.cited_by
