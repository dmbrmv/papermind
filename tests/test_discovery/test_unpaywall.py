"""Tests for Unpaywall DOI → PDF URL resolver."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from hydrofound.discovery.unpaywall import resolve_pdf_url


def _run(coro):
    return asyncio.run(coro)


def _mock_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


class TestResolvePdfUrl:
    def test_returns_pdf_url_from_best_oa_location(self) -> None:
        data = {
            "is_oa": True,
            "best_oa_location": {
                "url_for_pdf": "https://example.com/paper.pdf",
            },
            "oa_locations": [],
        }

        async def mock_get(url, **kwargs):
            return _mock_response(200, data)

        with patch("hydrofound.discovery.unpaywall.httpx.AsyncClient") as mock_cls:
            client = AsyncMock()
            client.get = mock_get
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = client

            result = _run(resolve_pdf_url("10.1234/test"))

        assert result == "https://example.com/paper.pdf"

    def test_falls_back_to_oa_locations(self) -> None:
        data = {
            "is_oa": True,
            "best_oa_location": {"url_for_pdf": ""},
            "oa_locations": [
                {"url_for_pdf": ""},
                {"url_for_pdf": "https://alt.com/paper.pdf"},
            ],
        }

        async def mock_get(url, **kwargs):
            return _mock_response(200, data)

        with patch("hydrofound.discovery.unpaywall.httpx.AsyncClient") as mock_cls:
            client = AsyncMock()
            client.get = mock_get
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = client

            result = _run(resolve_pdf_url("10.1234/test"))

        assert result == "https://alt.com/paper.pdf"

    def test_returns_none_when_no_pdf(self) -> None:
        data = {
            "is_oa": False,
            "best_oa_location": None,
            "oa_locations": [],
        }

        async def mock_get(url, **kwargs):
            return _mock_response(200, data)

        with patch("hydrofound.discovery.unpaywall.httpx.AsyncClient") as mock_cls:
            client = AsyncMock()
            client.get = mock_get
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = client

            result = _run(resolve_pdf_url("10.1234/closed"))

        assert result is None

    def test_returns_none_on_404(self) -> None:
        async def mock_get(url, **kwargs):
            return _mock_response(404)

        with patch("hydrofound.discovery.unpaywall.httpx.AsyncClient") as mock_cls:
            client = AsyncMock()
            client.get = mock_get
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = client

            result = _run(resolve_pdf_url("10.9999/nonexistent"))

        assert result is None

    def test_returns_none_for_empty_doi(self) -> None:
        result = _run(resolve_pdf_url(""))
        assert result is None

    def test_returns_none_on_network_error(self) -> None:
        import httpx

        with patch("hydrofound.discovery.unpaywall.httpx.AsyncClient") as mock_cls:
            client = AsyncMock()
            client.get = AsyncMock(side_effect=httpx.RequestError("timeout"))
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = client

            result = _run(resolve_pdf_url("10.1234/timeout"))

        assert result is None
