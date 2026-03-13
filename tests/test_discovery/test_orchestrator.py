"""Tests for the parallel discovery orchestrator."""

from __future__ import annotations

import pytest

from hydrofound.discovery.base import PaperResult
from hydrofound.discovery.orchestrator import _deduplicate, _merge_into, discover_papers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_paper(
    title: str = "A Paper",
    doi: str = "",
    year: int | None = None,
    abstract: str = "",
    pdf_url: str = "",
    authors: list[str] | None = None,
    source: str = "test",
) -> PaperResult:
    return PaperResult(
        title=title,
        doi=doi,
        year=year,
        abstract=abstract,
        pdf_url=pdf_url,
        authors=authors or [],
        source=source,
    )


class _MockProvider:
    """Synchronous-looking provider that returns a preset list."""

    def __init__(self, name: str, results: list[PaperResult]) -> None:
        self._name = name
        self._results = results

    @property
    def name(self) -> str:
        return self._name

    async def search(self, query: str, *, limit: int = 10) -> list[PaperResult]:
        return list(self._results)


class _FailingProvider:
    """Provider that always raises an exception."""

    @property
    def name(self) -> str:
        return "failing"

    async def search(self, query: str, *, limit: int = 10) -> list[PaperResult]:
        raise RuntimeError("provider exploded")


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


class TestParallelExecution:
    """Orchestrator queries all providers and merges their results."""

    @pytest.mark.asyncio
    async def test_results_from_all_providers_included(self) -> None:
        """Papers from every provider appear in the final output."""
        p1 = _MockProvider("p1", [_make_paper("Paper A", doi="10.1/A")])
        p2 = _MockProvider("p2", [_make_paper("Paper B", doi="10.1/B")])

        results = await discover_papers("hydrology", [p1, p2])

        titles = {r.title for r in results}
        assert "Paper A" in titles
        assert "Paper B" in titles

    @pytest.mark.asyncio
    async def test_exception_in_one_provider_does_not_crash_others(self) -> None:
        """A provider that raises must not prevent results from other providers."""
        good = _MockProvider("good", [_make_paper("Good Paper", doi="10.1/G")])
        bad = _FailingProvider()

        results = await discover_papers("hydrology", [good, bad])

        assert len(results) == 1
        assert results[0].title == "Good Paper"

    @pytest.mark.asyncio
    async def test_all_providers_fail_returns_empty_list(self) -> None:
        bad1 = _FailingProvider()
        bad2 = _FailingProvider()

        results = await discover_papers("hydrology", [bad1, bad2])

        assert results == []

    @pytest.mark.asyncio
    async def test_empty_providers_list_returns_empty(self) -> None:
        results = await discover_papers("hydrology", [])
        assert results == []

    @pytest.mark.asyncio
    async def test_limit_forwarded_to_each_provider(self) -> None:
        """The limit kwarg must be forwarded to every provider's search()."""
        received_limits: list[int] = []

        class CapturingProvider:
            @property
            def name(self) -> str:
                return "cap"

            async def search(self, query: str, *, limit: int = 10) -> list[PaperResult]:
                received_limits.append(limit)
                return []

        provider = CapturingProvider()
        await discover_papers("q", [provider], limit=7)

        assert received_limits == [7]


# ---------------------------------------------------------------------------
# Deduplication — DOI exact match
# ---------------------------------------------------------------------------


class TestDedupByDoi:
    """Results with the same DOI must be collapsed to one entry."""

    def test_same_doi_keeps_first_result(self) -> None:
        r1 = _make_paper("Paper X", doi="10.1/X", source="ss")
        r2 = _make_paper("Paper X duplicate", doi="10.1/X", source="exa")

        unique = _deduplicate([r1, r2])

        assert len(unique) == 1

    def test_different_dois_both_kept(self) -> None:
        r1 = _make_paper("Paper A", doi="10.1/A")
        r2 = _make_paper("Paper B", doi="10.1/B")

        unique = _deduplicate([r1, r2])

        assert len(unique) == 2

    def test_empty_doi_does_not_trigger_doi_dedup(self) -> None:
        """Two results with empty DOIs must NOT be collapsed by DOI logic alone."""
        r1 = _make_paper("Completely Different Title", doi="")
        r2 = _make_paper("Another Unique Title", doi="")

        unique = _deduplicate([r1, r2])

        assert len(unique) == 2


# ---------------------------------------------------------------------------
# Deduplication — fuzzy title + year
# ---------------------------------------------------------------------------


class TestDedupByFuzzyTitle:
    """Results with >90% similar titles are deduped based on year overlap."""

    def test_similar_title_same_year_deduplicated(self) -> None:
        r1 = _make_paper("Assessment of SWAT+ in Limpopo Basin", year=2021)
        r2 = _make_paper("Assessment of SWAT+ in Limpopo Basin.", year=2021)

        unique = _deduplicate([r1, r2])

        assert len(unique) == 1

    def test_similar_title_different_years_both_kept(self) -> None:
        r1 = _make_paper("Assessment of SWAT+ in Limpopo Basin", year=2020)
        r2 = _make_paper("Assessment of SWAT+ in Limpopo Basin", year=2021)

        unique = _deduplicate([r1, r2])

        assert len(unique) == 2

    def test_similar_title_one_year_none_deduplicated(self) -> None:
        """Year=None on either side means year is unknown → treat as same."""
        r1 = _make_paper("Assessment of SWAT+ in Limpopo Basin", year=2021)
        r2 = _make_paper("Assessment of SWAT+ in Limpopo Basin", year=None)

        unique = _deduplicate([r1, r2])

        assert len(unique) == 1

    def test_similar_title_both_years_none_deduplicated(self) -> None:
        r1 = _make_paper("Assessment of SWAT+ in Limpopo Basin", year=None)
        r2 = _make_paper("Assessment of SWAT+ in Limpopo Basin.", year=None)

        unique = _deduplicate([r1, r2])

        assert len(unique) == 1

    def test_dissimilar_titles_both_kept(self) -> None:
        r1 = _make_paper("SWAT+ Hydrological Model", year=2022)
        r2 = _make_paper("Deep Learning for Streamflow Prediction", year=2022)

        unique = _deduplicate([r1, r2])

        assert len(unique) == 2


# ---------------------------------------------------------------------------
# Metadata merging
# ---------------------------------------------------------------------------


class TestMetadataMerge:
    """When duplicates are found, metadata is merged into the first record."""

    def test_doi_filled_from_duplicate(self) -> None:
        r1 = _make_paper("Assessment of SWAT+ in Limpopo Basin", doi="", year=2021)
        r2 = _make_paper(
            "Assessment of SWAT+ in Limpopo Basin.", doi="10.1/SW", year=2021
        )

        unique = _deduplicate([r1, r2])

        assert len(unique) == 1
        assert unique[0].doi == "10.1/SW"

    def test_pdf_url_filled_from_duplicate(self) -> None:
        r1 = _make_paper("Assessment of SWAT+ in Limpopo Basin", pdf_url="", year=2021)
        r2 = _make_paper(
            "Assessment of SWAT+ in Limpopo Basin.",
            pdf_url="https://example.com/paper.pdf",
            year=2021,
        )

        unique = _deduplicate([r1, r2])

        assert unique[0].pdf_url == "https://example.com/paper.pdf"

    def test_abstract_filled_from_duplicate(self) -> None:
        r1 = _make_paper("Assessment of SWAT+ in Limpopo Basin", abstract="", year=2021)
        r2 = _make_paper(
            "Assessment of SWAT+ in Limpopo Basin.",
            abstract="This paper evaluates SWAT+.",
            year=2021,
        )

        unique = _deduplicate([r1, r2])

        assert unique[0].abstract == "This paper evaluates SWAT+."

    def test_year_filled_from_duplicate(self) -> None:
        r1 = _make_paper("Assessment of SWAT+ in Limpopo Basin", year=None)
        r2 = _make_paper("Assessment of SWAT+ in Limpopo Basin.", year=2021)

        unique = _deduplicate([r1, r2])

        assert unique[0].year == 2021

    def test_authors_filled_from_duplicate(self) -> None:
        r1 = _make_paper("Assessment of SWAT+ in Limpopo Basin", authors=[], year=2021)
        r2 = _make_paper(
            "Assessment of SWAT+ in Limpopo Basin.",
            authors=["Jeff Arnold"],
            year=2021,
        )

        unique = _deduplicate([r1, r2])

        assert unique[0].authors == ["Jeff Arnold"]

    def test_existing_fields_not_overwritten(self) -> None:
        """Fields already populated in target must not be overwritten by source."""
        r1 = _make_paper(
            "Assessment of SWAT+ in Limpopo Basin",
            doi="10.1/ORIGINAL",
            year=2021,
        )
        r2 = _make_paper(
            "Assessment of SWAT+ in Limpopo Basin.",
            doi="10.1/DIFFERENT",
            year=2021,
        )

        unique = _deduplicate([r1, r2])

        assert unique[0].doi == "10.1/ORIGINAL"


# ---------------------------------------------------------------------------
# _merge_into unit tests
# ---------------------------------------------------------------------------


class TestMergeInto:
    """Unit tests for the _merge_into helper."""

    def test_fills_doi(self) -> None:
        target = _make_paper("T", doi="")
        source = _make_paper("S", doi="10.1/X")
        _merge_into(target, source)
        assert target.doi == "10.1/X"

    def test_does_not_overwrite_doi(self) -> None:
        target = _make_paper("T", doi="10.1/KEEP")
        source = _make_paper("S", doi="10.1/IGNORE")
        _merge_into(target, source)
        assert target.doi == "10.1/KEEP"

    def test_fills_pdf_url(self) -> None:
        target = _make_paper("T", pdf_url="")
        source = _make_paper("S", pdf_url="https://example.com/paper.pdf")
        _merge_into(target, source)
        assert target.pdf_url == "https://example.com/paper.pdf"

    def test_fills_abstract(self) -> None:
        target = _make_paper("T", abstract="")
        source = _make_paper("S", abstract="Some abstract text.")
        _merge_into(target, source)
        assert target.abstract == "Some abstract text."

    def test_fills_year(self) -> None:
        target = _make_paper("T", year=None)
        source = _make_paper("S", year=2020)
        _merge_into(target, source)
        assert target.year == 2020

    def test_fills_authors(self) -> None:
        target = _make_paper("T", authors=[])
        source = _make_paper("S", authors=["Alice", "Bob"])
        _merge_into(target, source)
        assert target.authors == ["Alice", "Bob"]
