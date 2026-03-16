"""Parallel discovery orchestrator — runs multiple providers and deduplicates."""

from __future__ import annotations

import asyncio
from difflib import SequenceMatcher

from papermind.discovery.base import PaperResult, SearchProvider


async def discover_papers(
    query: str,
    providers: list[SearchProvider],
    *,
    limit: int = 10,
) -> list[PaperResult]:
    """Run search across all providers in parallel and deduplicate results.

    Providers are queried concurrently.  Any provider that raises an exception
    is silently skipped — its results are dropped but other providers proceed.

    Args:
        query: Free-text search query forwarded to every provider.
        providers: List of :class:`SearchProvider` instances to query.
        limit: Max results requested from each provider.

    Returns:
        Deduplicated list of :class:`PaperResult` objects.
    """
    tasks = [p.search(query, limit=limit) for p in providers]
    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    flat: list[PaperResult] = []
    for result in all_results:
        if isinstance(result, list):
            flat.extend(result)
        # Exception return values are silently skipped — provider already logs.

    return _deduplicate(flat)


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
