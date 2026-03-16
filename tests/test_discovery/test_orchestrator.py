"""Tests for the parallel discovery orchestrator."""

from __future__ import annotations

import pytest

from papermind.discovery.base import PaperResult
from papermind.discovery.orchestrator import (
    _deduplicate,
    _enrich_pdf_urls,
    _merge_into,
    discover_papers,
)

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


# ---------------------------------------------------------------------------
# Unpaywall enrichment
# ---------------------------------------------------------------------------


class TestUnpaywallEnrichment:
    """Orchestrator enriches missing pdf_urls via Unpaywall after dedup."""

    @pytest.mark.asyncio
    async def test_enriches_papers_with_doi_but_no_pdf_url(self) -> None:
        """Papers with DOI and no pdf_url should be resolved via Unpaywall."""
        from unittest.mock import AsyncMock, patch

        results = [
            _make_paper("Paper A", doi="10.1/A", pdf_url=""),
            _make_paper("Paper B", doi="10.1/B", pdf_url="https://existing.pdf"),
        ]

        with patch(
            "papermind.discovery.unpaywall.resolve_pdf_url",
            new_callable=AsyncMock,
            return_value="https://unpaywall.org/a.pdf",
        ) as mock_resolve:
            await _enrich_pdf_urls(results)

        # Only Paper A should have been resolved (Paper B already has pdf_url)
        mock_resolve.assert_called_once_with("10.1/A")
        assert results[0].pdf_url == "https://unpaywall.org/a.pdf"
        assert results[1].pdf_url == "https://existing.pdf"

    @pytest.mark.asyncio
    async def test_skips_papers_without_doi(self) -> None:
        """Papers without a DOI should not be sent to Unpaywall."""
        from unittest.mock import AsyncMock, patch

        results = [_make_paper("No DOI Paper", doi="", pdf_url="")]

        with patch(
            "papermind.discovery.unpaywall.resolve_pdf_url",
            new_callable=AsyncMock,
        ) as mock_resolve:
            await _enrich_pdf_urls(results)

        mock_resolve.assert_not_called()
        assert results[0].pdf_url == ""

    @pytest.mark.asyncio
    async def test_unpaywall_failure_leaves_pdf_url_empty(self) -> None:
        """If Unpaywall returns None, pdf_url stays empty."""
        from unittest.mock import AsyncMock, patch

        results = [_make_paper("Paper X", doi="10.1/X", pdf_url="")]

        with patch(
            "papermind.discovery.unpaywall.resolve_pdf_url",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await _enrich_pdf_urls(results)

        assert results[0].pdf_url == ""

    @pytest.mark.asyncio
    async def test_unpaywall_exception_does_not_crash(self) -> None:
        """An exception from Unpaywall should not crash enrichment."""
        from unittest.mock import AsyncMock, patch

        results = [_make_paper("Paper Y", doi="10.1/Y", pdf_url="")]

        with patch(
            "papermind.discovery.unpaywall.resolve_pdf_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network error"),
        ):
            await _enrich_pdf_urls(results)

        assert results[0].pdf_url == ""

    @pytest.mark.asyncio
    async def test_noop_when_all_have_pdf_urls(self) -> None:
        """No Unpaywall calls when every result already has a pdf_url."""
        from unittest.mock import AsyncMock, patch

        results = [
            _make_paper("A", doi="10.1/A", pdf_url="https://a.pdf"),
            _make_paper("B", doi="10.1/B", pdf_url="https://b.pdf"),
        ]

        with patch(
            "papermind.discovery.unpaywall.resolve_pdf_url",
            new_callable=AsyncMock,
        ) as mock_resolve:
            await _enrich_pdf_urls(results)

        mock_resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_discover_papers_calls_enrichment(self) -> None:
        """discover_papers should call _enrich_pdf_urls by default."""
        from unittest.mock import AsyncMock, patch

        provider = _MockProvider("test", [_make_paper("P", doi="10.1/P", pdf_url="")])

        with patch(
            "papermind.discovery.unpaywall.resolve_pdf_url",
            new_callable=AsyncMock,
            return_value="https://resolved.pdf",
        ):
            results = await discover_papers("q", [provider])

        assert results[0].pdf_url == "https://resolved.pdf"

    @pytest.mark.asyncio
    async def test_discover_papers_skips_enrichment_when_disabled(self) -> None:
        """enrich_unpaywall=False should skip Unpaywall calls."""
        from unittest.mock import AsyncMock, patch

        provider = _MockProvider("test", [_make_paper("P", doi="10.1/P", pdf_url="")])

        with patch(
            "papermind.discovery.unpaywall.resolve_pdf_url",
            new_callable=AsyncMock,
        ) as mock_resolve:
            results = await discover_papers("q", [provider], enrich_unpaywall=False)

        mock_resolve.assert_not_called()
        assert results[0].pdf_url == ""


# ---------------------------------------------------------------------------
# Result ranking
# ---------------------------------------------------------------------------


class TestScoreResult:
    """Unit tests for the _score_result scoring function."""

    def test_doi_adds_3(self) -> None:
        from papermind.discovery.orchestrator import _score_result

        r = _make_paper("Some Title", doi="10.1/X")
        assert _score_result(r) >= 3

    def test_pdf_url_adds_3(self) -> None:
        from papermind.discovery.orchestrator import _score_result

        r = _make_paper("Some Title", pdf_url="https://example.com/paper.pdf")
        assert _score_result(r) >= 3

    def test_academic_title_adds_2(self) -> None:
        from papermind.discovery.orchestrator import _score_result

        r = _make_paper("Assessment of SWAT+ model calibration")
        assert _score_result(r) >= 2

    def test_non_academic_title_no_bonus(self) -> None:
        from papermind.discovery.orchestrator import _score_result

        r = _make_paper("Random thoughts about stuff")
        assert _score_result(r) == 0

    def test_academic_domain_adds_1(self) -> None:
        from papermind.discovery.orchestrator import _score_result

        r = _make_paper("Paper", pdf_url="https://arxiv.org/pdf/2301.12345.pdf")
        # pdf_url (+3) + academic domain (+1) = at least 4
        assert _score_result(r) >= 4

    def test_edu_domain_adds_1(self) -> None:
        from papermind.discovery.orchestrator import _score_result

        r = _make_paper("Paper", pdf_url="https://www.stanford.edu/paper.pdf")
        assert _score_result(r) >= 4

    def test_noise_domain_subtracts_3(self) -> None:
        from papermind.discovery.orchestrator import _score_result

        r = _make_paper("Paper", pdf_url="https://linkedin.com/post/12345")
        # pdf_url (+3) + noise (-3) = 0
        assert _score_result(r) == 0

    def test_full_score_paper(self) -> None:
        """Paper with DOI, pdf_url on arxiv, and academic title scores 9."""
        from papermind.discovery.orchestrator import _score_result

        r = _make_paper(
            "Assessment of hydrological modeling",
            doi="10.1/X",
            pdf_url="https://arxiv.org/pdf/paper.pdf",
        )
        # doi(+3) + pdf_url(+3) + academic_title(+2) + academic_domain(+1) = 9
        assert _score_result(r) == 9


class TestExtractDomain:
    """Unit tests for _extract_domain helper."""

    def test_simple_url(self) -> None:
        from papermind.discovery.orchestrator import _extract_domain

        assert _extract_domain("https://arxiv.org/pdf/123.pdf") == "arxiv.org"

    def test_www_stripped(self) -> None:
        from papermind.discovery.orchestrator import _extract_domain

        assert _extract_domain("https://www.nature.com/articles/123") == "nature.com"

    def test_empty_url(self) -> None:
        from papermind.discovery.orchestrator import _extract_domain

        assert _extract_domain("") == ""

    def test_invalid_url(self) -> None:
        from papermind.discovery.orchestrator import _extract_domain

        assert _extract_domain("not-a-url") == ""


class TestRankResults:
    """Integration tests for _rank_results ordering."""

    def test_higher_score_comes_first(self) -> None:
        from papermind.discovery.orchestrator import _rank_results

        low = _make_paper("Random blog post")
        high = _make_paper(
            "Assessment of SWAT+ calibration",
            doi="10.1/X",
            pdf_url="https://arxiv.org/paper.pdf",
        )

        ranked = _rank_results([low, high])
        assert ranked[0] is high
        assert ranked[1] is low

    def test_no_results_dropped(self) -> None:
        from papermind.discovery.orchestrator import _rank_results

        papers = [
            _make_paper("A"),
            _make_paper("B", doi="10.1/B"),
            _make_paper("C", pdf_url="https://c.pdf"),
        ]

        ranked = _rank_results(papers)
        assert len(ranked) == 3

    def test_stable_sort_for_equal_scores(self) -> None:
        """Results with equal scores should maintain relative order."""
        from papermind.discovery.orchestrator import _rank_results

        a = _make_paper("Paper Alpha")
        b = _make_paper("Paper Beta")

        ranked = _rank_results([a, b])
        assert ranked[0] is a
        assert ranked[1] is b
