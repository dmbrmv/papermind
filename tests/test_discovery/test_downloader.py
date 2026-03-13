"""Tests for the paper download engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from hydrofound.discovery.base import PaperResult
from hydrofound.discovery.downloader import (
    _is_valid_pdf,
    download_paper,
    load_last_search,
    pick_results,
    rewrite_arxiv_url,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_paper(
    title: str = "Test Paper",
    doi: str = "",
    pdf_url: str = "https://example.com/paper.pdf",
    is_open_access: bool = False,
    year: int | None = None,
) -> PaperResult:
    return PaperResult(
        title=title,
        doi=doi,
        pdf_url=pdf_url,
        is_open_access=is_open_access,
        year=year,
    )


_PDF_BYTES = b"%PDF-1.4 fake content"
_HTML_BYTES = b"<html><body>paywall</body></html>"


# ---------------------------------------------------------------------------
# 1. arXiv URL rewriting
# ---------------------------------------------------------------------------


class TestRewriteArxivUrl:
    """arXiv abs/ URLs must be converted to pdf/ with .pdf suffix."""

    def test_abs_to_pdf(self) -> None:
        url = "https://arxiv.org/abs/2301.12345"
        assert rewrite_arxiv_url(url) == "https://arxiv.org/pdf/2301.12345.pdf"

    def test_already_pdf_no_suffix(self) -> None:
        url = "https://arxiv.org/pdf/2301.12345"
        assert rewrite_arxiv_url(url) == "https://arxiv.org/pdf/2301.12345.pdf"

    def test_already_pdf_with_suffix_unchanged(self) -> None:
        url = "https://arxiv.org/pdf/2301.12345.pdf"
        assert rewrite_arxiv_url(url) == "https://arxiv.org/pdf/2301.12345.pdf"

    def test_non_arxiv_url_unchanged(self) -> None:
        url = "https://example.com/paper.pdf"
        assert rewrite_arxiv_url(url) == "https://example.com/paper.pdf"

    def test_non_arxiv_abs_unchanged(self) -> None:
        url = "https://example.com/abs/12345"
        assert rewrite_arxiv_url(url) == "https://example.com/abs/12345"


# ---------------------------------------------------------------------------
# 2. Magic bytes validation
# ---------------------------------------------------------------------------


class TestIsValidPdf:
    """Only content starting with %PDF- is accepted."""

    def test_valid_pdf_bytes(self) -> None:
        assert _is_valid_pdf(b"%PDF-1.4 content") is True

    def test_html_bytes_invalid(self) -> None:
        assert _is_valid_pdf(b"<html>not a pdf") is False

    def test_empty_bytes_invalid(self) -> None:
        assert _is_valid_pdf(b"") is False

    def test_short_bytes_invalid(self) -> None:
        assert _is_valid_pdf(b"%PDF") is False  # only 4 bytes, needs 5

    def test_exactly_five_pdf_bytes(self) -> None:
        assert _is_valid_pdf(b"%PDF-") is True


# ---------------------------------------------------------------------------
# 3. Direct HTTP download — success
# ---------------------------------------------------------------------------


class TestDownloadPaper:
    """download_paper fetches, validates, and saves PDF files."""

    @pytest.mark.asyncio
    async def test_successful_download_writes_file(self, tmp_path: Path) -> None:
        paper = _make_paper(
            title="Green Ampt Infiltration", pdf_url="https://example.com/paper.pdf"
        )

        mock_response = MagicMock()
        mock_response.content = _PDF_BYTES
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "hydrofound.discovery.downloader.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await download_paper(paper, tmp_path)

        assert result is not None
        assert result.exists()
        assert result.read_bytes() == _PDF_BYTES

    @pytest.mark.asyncio
    async def test_file_named_from_title_slug(self, tmp_path: Path) -> None:
        paper = _make_paper(
            title="SWAT Plus Model 2021", pdf_url="https://example.com/p.pdf"
        )

        mock_response = MagicMock()
        mock_response.content = _PDF_BYTES
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "hydrofound.discovery.downloader.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await download_paper(paper, tmp_path)

        assert result is not None
        assert "swat" in result.name.lower()
        assert result.suffix == ".pdf"

    @pytest.mark.asyncio
    async def test_output_dir_created_if_missing(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "nested" / "pdfs"
        paper = _make_paper(pdf_url="https://example.com/paper.pdf")

        mock_response = MagicMock()
        mock_response.content = _PDF_BYTES
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "hydrofound.discovery.downloader.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await download_paper(paper, output_dir)

        assert result is not None
        assert output_dir.exists()


# ---------------------------------------------------------------------------
# 4. Magic bytes failure — non-PDF content → returns None
# ---------------------------------------------------------------------------


class TestDownloadPaperInvalidContent:
    """Non-PDF responses (HTML paywall, etc.) must be rejected."""

    @pytest.mark.asyncio
    async def test_html_response_returns_none(self, tmp_path: Path) -> None:
        paper = _make_paper(pdf_url="https://example.com/paper.pdf")

        mock_response = MagicMock()
        mock_response.content = _HTML_BYTES
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "hydrofound.discovery.downloader.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await download_paper(paper, tmp_path)

        assert result is None

    @pytest.mark.asyncio
    async def test_no_file_written_on_invalid_content(self, tmp_path: Path) -> None:
        paper = _make_paper(pdf_url="https://example.com/paper.pdf")

        mock_response = MagicMock()
        mock_response.content = _HTML_BYTES
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "hydrofound.discovery.downloader.httpx.AsyncClient",
            return_value=mock_client,
        ):
            await download_paper(paper, tmp_path)

        assert list(tmp_path.glob("*.pdf")) == []


# ---------------------------------------------------------------------------
# 5. 404 / timeout → None, no crash
# ---------------------------------------------------------------------------


class TestDownloadPaperNetworkErrors:
    """Network failures must return None without raising."""

    @pytest.mark.asyncio
    async def test_http_404_returns_none(self, tmp_path: Path) -> None:
        paper = _make_paper(pdf_url="https://example.com/missing.pdf")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "hydrofound.discovery.downloader.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await download_paper(paper, tmp_path)

        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self, tmp_path: Path) -> None:
        paper = _make_paper(pdf_url="https://example.com/slow.pdf")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch(
            "hydrofound.discovery.downloader.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await download_paper(paper, tmp_path)

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_pdf_url_returns_none(self, tmp_path: Path) -> None:
        paper = _make_paper(pdf_url="")
        result = await download_paper(paper, tmp_path)
        assert result is None

    @pytest.mark.asyncio
    async def test_connection_error_returns_none(self, tmp_path: Path) -> None:
        paper = _make_paper(pdf_url="https://example.com/paper.pdf")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with patch(
            "hydrofound.discovery.downloader.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await download_paper(paper, tmp_path)

        assert result is None


# ---------------------------------------------------------------------------
# 6. arXiv URL rewriting inside download_paper
# ---------------------------------------------------------------------------


class TestDownloadPaperArxiv:
    """arXiv abs/ URLs must be rewritten before the HTTP call."""

    @pytest.mark.asyncio
    async def test_arxiv_abs_url_rewritten(self, tmp_path: Path) -> None:
        paper = _make_paper(pdf_url="https://arxiv.org/abs/2301.12345")

        captured_urls: list[str] = []

        mock_response = MagicMock()
        mock_response.content = _PDF_BYTES
        mock_response.raise_for_status = MagicMock()

        async def fake_get(url: str, **kwargs: object) -> MagicMock:
            captured_urls.append(url)
            return mock_response

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = fake_get

        with patch(
            "hydrofound.discovery.downloader.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await download_paper(paper, tmp_path)

        assert result is not None
        assert captured_urls[0] == "https://arxiv.org/pdf/2301.12345.pdf"


# ---------------------------------------------------------------------------
# 7. load_last_search
# ---------------------------------------------------------------------------


class TestLoadLastSearch:
    """Load search results from the last_search.json cache."""

    def test_loads_results_from_cache(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".hydrofound"
        cache_dir.mkdir()
        payload = {
            "query": "SWAT+",
            "results": [
                {
                    "title": "Paper A",
                    "authors": ["Alice"],
                    "year": 2021,
                    "doi": "10.1/A",
                    "abstract": "Abstract A",
                    "pdf_url": "https://example.com/a.pdf",
                    "source": "semantic_scholar",
                    "is_open_access": True,
                    "venue": "JH",
                    "citation_count": 42,
                }
            ],
        }
        (cache_dir / "last_search.json").write_text(json.dumps(payload))

        results = load_last_search(tmp_path)

        assert len(results) == 1
        r = results[0]
        assert r.title == "Paper A"
        assert r.authors == ["Alice"]
        assert r.year == 2021
        assert r.doi == "10.1/A"
        assert r.pdf_url == "https://example.com/a.pdf"
        assert r.is_open_access is True
        assert r.venue == "JH"
        assert r.citation_count == 42

    def test_missing_cache_returns_empty_list(self, tmp_path: Path) -> None:
        results = load_last_search(tmp_path)
        assert results == []

    def test_multiple_results_loaded(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".hydrofound"
        cache_dir.mkdir()
        payload = {
            "query": "hydrology",
            "results": [{"title": f"Paper {i}", "pdf_url": ""} for i in range(5)],
        }
        (cache_dir / "last_search.json").write_text(json.dumps(payload))

        results = load_last_search(tmp_path)
        assert len(results) == 5

    def test_missing_optional_fields_have_defaults(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".hydrofound"
        cache_dir.mkdir()
        payload = {"results": [{"title": "Minimal Paper"}]}
        (cache_dir / "last_search.json").write_text(json.dumps(payload))

        results = load_last_search(tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r.doi == ""
        assert r.pdf_url == ""
        assert r.year is None
        assert r.authors == []
        assert r.is_open_access is False


# ---------------------------------------------------------------------------
# 8. pick_results
# ---------------------------------------------------------------------------


class TestPickResults:
    """Select results by 1-based comma-separated index string."""

    def _papers(self, n: int = 5) -> list[PaperResult]:
        return [_make_paper(title=f"Paper {i + 1}") for i in range(n)]

    def test_picks_single_index(self) -> None:
        papers = self._papers()
        picked = pick_results(papers, "1")
        assert len(picked) == 1
        assert picked[0].title == "Paper 1"

    def test_picks_multiple_indices(self) -> None:
        papers = self._papers()
        picked = pick_results(papers, "1,3")
        assert len(picked) == 2
        assert picked[0].title == "Paper 1"
        assert picked[1].title == "Paper 3"

    def test_picks_non_contiguous(self) -> None:
        papers = self._papers()
        picked = pick_results(papers, "2,4,5")
        titles = [p.title for p in picked]
        assert titles == ["Paper 2", "Paper 4", "Paper 5"]

    def test_out_of_range_index_skipped(self) -> None:
        papers = self._papers(3)
        picked = pick_results(papers, "1,99")
        assert len(picked) == 1
        assert picked[0].title == "Paper 1"

    def test_empty_indices_returns_empty(self) -> None:
        papers = self._papers()
        picked = pick_results(papers, "")
        assert picked == []

    def test_whitespace_in_indices_handled(self) -> None:
        papers = self._papers()
        picked = pick_results(papers, "1, 3, 5")
        assert len(picked) == 3

    def test_all_indices_valid(self) -> None:
        papers = self._papers(5)
        picked = pick_results(papers, "1,2,3,4,5")
        assert len(picked) == 5

    def test_non_numeric_index_skipped(self) -> None:
        papers = self._papers()
        picked = pick_results(papers, "1,abc,3")
        assert len(picked) == 2


# ---------------------------------------------------------------------------
# 9. Open-access filtering (tested via pick_results + is_open_access flag)
# ---------------------------------------------------------------------------


class TestOpenAccessFiltering:
    """Open-access filtering logic used in the CLI."""

    def test_filter_keeps_open_access_only(self) -> None:
        papers = [
            _make_paper(title="Open Paper", is_open_access=True),
            _make_paper(title="Closed Paper", is_open_access=False),
            _make_paper(title="Open Paper 2", is_open_access=True),
        ]
        open_access = [r for r in papers if r.is_open_access]
        assert len(open_access) == 2
        assert all(p.is_open_access for p in open_access)

    def test_filter_empty_when_none_open_access(self) -> None:
        papers = [_make_paper(is_open_access=False) for _ in range(3)]
        open_access = [r for r in papers if r.is_open_access]
        assert open_access == []
