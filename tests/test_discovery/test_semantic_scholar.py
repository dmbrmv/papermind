"""Tests for the Semantic Scholar search provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from hydrofound.discovery.base import PaperResult
from hydrofound.discovery.semantic_scholar import _BASE_URL, SemanticScholarProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PAPER_RAW = {
    "title": "Soil and Water Assessment Tool: A Historical Perspective",
    "authors": [
        {"authorId": "1", "name": "Jeff Arnold"},
        {"authorId": "2", "name": "Raghavan Srinivasan"},
    ],
    "year": 2012,
    "abstract": "The SWAT model is a widely used watershed simulation tool.",
    "externalIds": {"DOI": "10.1007/s11269-012-0017-2", "MAG": "123456"},
    "isOpenAccess": True,
    "venue": "Water Resources Management",
    "citationCount": 842,
    "openAccessPdf": {"url": "https://example.com/swat2012.pdf", "status": "GREEN"},
}

_CLOSED_PAPER_RAW = {
    "title": "Closed Access Paper on Hydrology",
    "authors": [{"authorId": "3", "name": "Jane Doe"}],
    "year": 2021,
    "abstract": "",
    "externalIds": {"DOI": "10.1234/closed.2021"},
    "isOpenAccess": False,
    "venue": "Journal of Hydrology",
    "citationCount": 5,
    "openAccessPdf": None,
}


def _make_response(data: list[dict], status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response for a paper search."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = {"total": len(data), "offset": 0, "data": data}
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
        resp.text = f"Error {status_code}"
    else:
        resp.raise_for_status.return_value = None
    return resp


def _patch_client(response: MagicMock) -> patch:
    """Patch httpx.AsyncClient so .get() returns *response*."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return patch(
        "hydrofound.discovery.semantic_scholar.httpx.AsyncClient",
        return_value=mock_client,
    )


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------


class TestQueryConstruction:
    """Verify the correct URL, params, and headers are sent to httpx."""

    @pytest.mark.asyncio
    async def test_correct_base_url(self) -> None:
        """GET request must target the Semantic Scholar paper/search endpoint."""
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp) as mock_cls:
            provider = SemanticScholarProvider()
            await provider.search("SWAT hydrology")

        client_instance = mock_cls.return_value
        call_kwargs = client_instance.get.call_args
        assert call_kwargs[0][0] == _BASE_URL

    @pytest.mark.asyncio
    async def test_query_param_forwarded(self) -> None:
        """The *query* string must appear in the request params."""
        resp = _make_response([])
        with _patch_client(resp) as mock_cls:
            provider = SemanticScholarProvider()
            await provider.search("Green Ampt infiltration")

        client_instance = mock_cls.return_value
        params = client_instance.get.call_args[1]["params"]
        assert params["query"] == "Green Ampt infiltration"

    @pytest.mark.asyncio
    async def test_limit_param_forwarded(self) -> None:
        """The *limit* keyword argument must be passed as the ``limit`` param."""
        resp = _make_response([])
        with _patch_client(resp) as mock_cls:
            provider = SemanticScholarProvider()
            await provider.search("evapotranspiration", limit=5)

        client_instance = mock_cls.return_value
        params = client_instance.get.call_args[1]["params"]
        assert params["limit"] == 5

    @pytest.mark.asyncio
    async def test_fields_param_present(self) -> None:
        """The ``fields`` param must be set (non-empty)."""
        resp = _make_response([])
        with _patch_client(resp) as mock_cls:
            provider = SemanticScholarProvider()
            await provider.search("watershed delineation")

        client_instance = mock_cls.return_value
        params = client_instance.get.call_args[1]["params"]
        assert "fields" in params
        assert params["fields"]  # non-empty

    @pytest.mark.asyncio
    async def test_no_api_key_header_when_not_configured(self) -> None:
        """No ``x-api-key`` header when provider is created without a key."""
        resp = _make_response([])
        with _patch_client(resp) as mock_cls:
            provider = SemanticScholarProvider()
            await provider.search("baseflow recession")

        client_instance = mock_cls.return_value
        headers = client_instance.get.call_args[1]["headers"]
        assert "x-api-key" not in headers

    @pytest.mark.asyncio
    async def test_api_key_header_sent_when_configured(self) -> None:
        """``x-api-key`` header must be present when an API key is provided."""
        resp = _make_response([])
        with _patch_client(resp) as mock_cls:
            provider = SemanticScholarProvider(api_key="test-secret-key")
            await provider.search("streamflow prediction")

        client_instance = mock_cls.return_value
        headers = client_instance.get.call_args[1]["headers"]
        assert headers["x-api-key"] == "test-secret-key"


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


class TestResponseParsing:
    """Verify correct mapping from raw API data to PaperResult."""

    @pytest.mark.asyncio
    async def test_returns_list_of_paper_results(self) -> None:
        """search() returns a list of PaperResult instances."""
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            provider = SemanticScholarProvider()
            results = await provider.search("SWAT")

        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], PaperResult)

    @pytest.mark.asyncio
    async def test_title_parsed(self) -> None:
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert results[0].title == _PAPER_RAW["title"]

    @pytest.mark.asyncio
    async def test_authors_parsed(self) -> None:
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert results[0].authors == ["Jeff Arnold", "Raghavan Srinivasan"]

    @pytest.mark.asyncio
    async def test_year_parsed(self) -> None:
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert results[0].year == 2012

    @pytest.mark.asyncio
    async def test_abstract_parsed(self) -> None:
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert "watershed simulation" in results[0].abstract

    @pytest.mark.asyncio
    async def test_venue_parsed(self) -> None:
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert results[0].venue == "Water Resources Management"

    @pytest.mark.asyncio
    async def test_citation_count_parsed(self) -> None:
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert results[0].citation_count == 842

    @pytest.mark.asyncio
    async def test_source_is_semantic_scholar(self) -> None:
        """PaperResult.source must be 'semantic_scholar'."""
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert results[0].source == "semantic_scholar"

    @pytest.mark.asyncio
    async def test_multiple_results_returned(self) -> None:
        resp = _make_response([_PAPER_RAW, _CLOSED_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("hydrology")

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty_list(self) -> None:
        resp = _make_response([])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("no results query")

        assert results == []


# ---------------------------------------------------------------------------
# DOI extraction
# ---------------------------------------------------------------------------


class TestDoiExtraction:
    """DOI must be pulled from externalIds.DOI."""

    @pytest.mark.asyncio
    async def test_doi_extracted_from_external_ids(self) -> None:
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert results[0].doi == "10.1007/s11269-012-0017-2"

    @pytest.mark.asyncio
    async def test_doi_empty_when_external_ids_missing(self) -> None:
        raw = dict(_PAPER_RAW)
        raw["externalIds"] = None
        resp = _make_response([raw])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert results[0].doi == ""

    @pytest.mark.asyncio
    async def test_doi_empty_when_doi_key_absent(self) -> None:
        raw = dict(_PAPER_RAW)
        raw["externalIds"] = {"MAG": "999"}  # DOI key not present
        resp = _make_response([raw])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert results[0].doi == ""


# ---------------------------------------------------------------------------
# Open access detection
# ---------------------------------------------------------------------------


class TestOpenAccessDetection:
    """is_open_access and pdf_url must be set correctly."""

    @pytest.mark.asyncio
    async def test_open_access_true_when_flagged(self) -> None:
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert results[0].is_open_access is True

    @pytest.mark.asyncio
    async def test_open_access_false_for_closed_paper(self) -> None:
        resp = _make_response([_CLOSED_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("closed")

        assert results[0].is_open_access is False

    @pytest.mark.asyncio
    async def test_pdf_url_extracted_from_open_access_pdf(self) -> None:
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("SWAT")

        assert results[0].pdf_url == "https://example.com/swat2012.pdf"

    @pytest.mark.asyncio
    async def test_pdf_url_empty_when_open_access_pdf_is_none(self) -> None:
        resp = _make_response([_CLOSED_PAPER_RAW])
        with _patch_client(resp):
            results = await SemanticScholarProvider().search("closed")

        assert results[0].pdf_url == ""


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Provider must return empty list on errors, never raise."""

    @pytest.mark.asyncio
    async def test_api_down_returns_empty_list(self) -> None:
        """RequestError (connection refused, etc.) → empty list."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.RequestError("Connection refused", request=MagicMock())
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "hydrofound.discovery.semantic_scholar.httpx.AsyncClient",
            return_value=mock_client,
        ):
            provider = SemanticScholarProvider()
            results = await provider.search("any query")

        assert results == []

    @pytest.mark.asyncio
    async def test_rate_limited_returns_empty_list(self) -> None:
        """HTTP 429 (rate limited) → empty list."""
        resp = _make_response([], status_code=429)
        with _patch_client(resp):
            provider = SemanticScholarProvider()
            results = await provider.search("any query")

        assert results == []

    @pytest.mark.asyncio
    async def test_server_error_returns_empty_list(self) -> None:
        """HTTP 500 → empty list."""
        resp = _make_response([], status_code=500)
        with _patch_client(resp):
            provider = SemanticScholarProvider()
            results = await provider.search("any query")

        assert results == []

    @pytest.mark.asyncio
    async def test_unauthorized_returns_empty_list(self) -> None:
        """HTTP 403 (bad API key, etc.) → empty list."""
        resp = _make_response([], status_code=403)
        with _patch_client(resp):
            provider = SemanticScholarProvider()
            results = await provider.search("any query")

        assert results == []


# ---------------------------------------------------------------------------
# Provider identity
# ---------------------------------------------------------------------------


class TestProviderIdentity:
    """Verify the provider's name property."""

    def test_name_is_semantic_scholar(self) -> None:
        provider = SemanticScholarProvider()
        assert provider.name == "semantic_scholar"

    def test_name_unchanged_with_api_key(self) -> None:
        provider = SemanticScholarProvider(api_key="some-key")
        assert provider.name == "semantic_scholar"
