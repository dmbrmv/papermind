"""Tests for the Exa search provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from hydrofound.discovery.base import PaperResult
from hydrofound.discovery.exa import _EXA_SEARCH_URL, ExaProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PAPER_RAW = {
    "title": "SWAT+ Hydrological Model: Development and Applications",
    "text": "SWAT+ is a complete restructuring of the SWAT model.",
    "url": "https://example.com/swatplus.pdf",
    "id": "exa-id-1",
    "score": 0.95,
    "publishedDate": "2022-01-15",
    "author": "Jeffrey Arnold",
}

_MINIMAL_PAPER_RAW = {
    "title": "Minimal Paper",
    "text": "",
    "url": "",
}


def _make_response(items: list[dict], status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response for an Exa search."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = {"results": items, "requestId": "test-req-id"}
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
    """Patch httpx.AsyncClient so .post() returns *response*."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return patch(
        "hydrofound.discovery.exa.httpx.AsyncClient",
        return_value=mock_client,
    )


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------


class TestQueryConstruction:
    """Verify correct URL, payload, and headers are sent to httpx."""

    @pytest.mark.asyncio
    async def test_correct_endpoint_url(self) -> None:
        """POST request must target the Exa search endpoint."""
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp) as mock_cls:
            provider = ExaProvider(api_key="test-key")
            await provider.search("SWAT hydrology")

        client_instance = mock_cls.return_value
        call_args = client_instance.post.call_args
        assert call_args[0][0] == _EXA_SEARCH_URL

    @pytest.mark.asyncio
    async def test_query_in_payload(self) -> None:
        """The query string must appear in the JSON body as ``query``."""
        resp = _make_response([])
        with _patch_client(resp) as mock_cls:
            provider = ExaProvider(api_key="test-key")
            await provider.search("Green Ampt infiltration")

        client_instance = mock_cls.return_value
        payload = client_instance.post.call_args[1]["json"]
        assert payload["query"] == "Green Ampt infiltration"

    @pytest.mark.asyncio
    async def test_num_results_in_payload(self) -> None:
        """The limit must appear in the payload as ``numResults``."""
        resp = _make_response([])
        with _patch_client(resp) as mock_cls:
            provider = ExaProvider(api_key="test-key")
            await provider.search("evapotranspiration", limit=5)

        client_instance = mock_cls.return_value
        payload = client_instance.post.call_args[1]["json"]
        assert payload["numResults"] == 5

    @pytest.mark.asyncio
    async def test_contents_field_present(self) -> None:
        """Payload must include ``contents`` to request text snippets."""
        resp = _make_response([])
        with _patch_client(resp) as mock_cls:
            provider = ExaProvider(api_key="test-key")
            await provider.search("baseflow recession")

        client_instance = mock_cls.return_value
        payload = client_instance.post.call_args[1]["json"]
        assert "contents" in payload

    @pytest.mark.asyncio
    async def test_api_key_header_sent(self) -> None:
        """``x-api-key`` header must carry the configured API key."""
        resp = _make_response([])
        with _patch_client(resp) as mock_cls:
            provider = ExaProvider(api_key="my-exa-key")
            await provider.search("streamflow prediction")

        client_instance = mock_cls.return_value
        headers = client_instance.post.call_args[1]["headers"]
        assert headers["x-api-key"] == "my-exa-key"


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


class TestResponseParsing:
    """Verify correct mapping from raw API data to PaperResult."""

    @pytest.mark.asyncio
    async def test_returns_list_of_paper_results(self) -> None:
        """search() must return a list of PaperResult instances."""
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            provider = ExaProvider(api_key="test-key")
            results = await provider.search("SWAT")

        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], PaperResult)

    @pytest.mark.asyncio
    async def test_title_parsed(self) -> None:
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await ExaProvider(api_key="k").search("SWAT")

        assert results[0].title == _PAPER_RAW["title"]

    @pytest.mark.asyncio
    async def test_abstract_from_text_field(self) -> None:
        """``text`` field maps to ``abstract``."""
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await ExaProvider(api_key="k").search("SWAT")

        assert results[0].abstract == _PAPER_RAW["text"]

    @pytest.mark.asyncio
    async def test_pdf_url_from_url_field(self) -> None:
        """``url`` field maps to ``pdf_url``."""
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await ExaProvider(api_key="k").search("SWAT")

        assert results[0].pdf_url == _PAPER_RAW["url"]

    @pytest.mark.asyncio
    async def test_source_is_exa(self) -> None:
        """PaperResult.source must be ``'exa'``."""
        resp = _make_response([_PAPER_RAW])
        with _patch_client(resp):
            results = await ExaProvider(api_key="k").search("SWAT")

        assert results[0].source == "exa"

    @pytest.mark.asyncio
    async def test_multiple_results_returned(self) -> None:
        resp = _make_response([_PAPER_RAW, _MINIMAL_PAPER_RAW])
        with _patch_client(resp):
            results = await ExaProvider(api_key="k").search("hydrology")

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_empty_results_list(self) -> None:
        resp = _make_response([])
        with _patch_client(resp):
            results = await ExaProvider(api_key="k").search("no results")

        assert results == []

    @pytest.mark.asyncio
    async def test_missing_title_defaults_to_empty_string(self) -> None:
        raw = {"text": "some text", "url": "https://example.com"}
        resp = _make_response([raw])
        with _patch_client(resp):
            results = await ExaProvider(api_key="k").search("query")

        assert results[0].title == ""

    @pytest.mark.asyncio
    async def test_missing_url_defaults_to_empty_string(self) -> None:
        raw = {"title": "Some Paper", "text": "snippet"}
        resp = _make_response([raw])
        with _patch_client(resp):
            results = await ExaProvider(api_key="k").search("query")

        assert results[0].pdf_url == ""


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Provider must return empty list on errors, never raise."""

    @pytest.mark.asyncio
    async def test_connection_error_returns_empty_list(self) -> None:
        """RequestError (connection refused, etc.) → empty list."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.RequestError("Connection refused", request=MagicMock())
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "hydrofound.discovery.exa.httpx.AsyncClient",
            return_value=mock_client,
        ):
            provider = ExaProvider(api_key="k")
            results = await provider.search("any query")

        assert results == []

    @pytest.mark.asyncio
    async def test_rate_limited_returns_empty_list(self) -> None:
        """HTTP 429 → empty list."""
        resp = _make_response([], status_code=429)
        with _patch_client(resp):
            results = await ExaProvider(api_key="k").search("any query")

        assert results == []

    @pytest.mark.asyncio
    async def test_unauthorized_returns_empty_list(self) -> None:
        """HTTP 401 (bad API key) → empty list."""
        resp = _make_response([], status_code=401)
        with _patch_client(resp):
            results = await ExaProvider(api_key="bad-key").search("any query")

        assert results == []

    @pytest.mark.asyncio
    async def test_server_error_returns_empty_list(self) -> None:
        """HTTP 500 → empty list."""
        resp = _make_response([], status_code=500)
        with _patch_client(resp):
            results = await ExaProvider(api_key="k").search("any query")

        assert results == []


# ---------------------------------------------------------------------------
# Provider identity
# ---------------------------------------------------------------------------


class TestProviderIdentity:
    """Verify the provider's name property."""

    def test_name_is_exa(self) -> None:
        provider = ExaProvider(api_key="k")
        assert provider.name == "exa"

    def test_name_unchanged_regardless_of_key(self) -> None:
        provider = ExaProvider(api_key="some-other-key")
        assert provider.name == "exa"
