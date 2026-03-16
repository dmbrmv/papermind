"""Exa search API provider for academic paper discovery."""

from __future__ import annotations

import logging

import httpx

from papermind.discovery.base import PaperResult

logger = logging.getLogger(__name__)

_EXA_SEARCH_URL = "https://api.exa.ai/search"


class ExaProvider:
    """Search provider backed by the Exa neural search API.

    Args:
        api_key: Exa API key sent as ``x-api-key`` header.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self._timeout = timeout

    @property
    def name(self) -> str:
        """Provider name."""
        return "exa"

    async def search(self, query: str, *, limit: int = 10) -> list[PaperResult]:
        """Search Exa for papers matching *query*.

        Args:
            query: Free-text search query.
            limit: Maximum number of results to return.

        Returns:
            List of :class:`PaperResult` objects.  Returns an empty list on
            any HTTP or API error rather than raising.
        """
        payload = {
            "query": query,
            "numResults": limit,
            "type": "auto",
            "contents": {"text": {"maxCharacters": 500}},
        }
        headers = {"x-api-key": self.api_key}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    _EXA_SEARCH_URL,
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Exa API error %s: %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return []
        except httpx.RequestError as exc:
            logger.warning("Exa request failed: %s", exc)
            return []

        results: list[PaperResult] = []
        for item in data.get("results", []):
            results.append(
                PaperResult(
                    title=item.get("title", ""),
                    abstract=item.get("text", ""),
                    source=self.name,
                    pdf_url=item.get("url", ""),
                )
            )
        return results
