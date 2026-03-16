"""OpenAlex search provider — free, no API key, direct PDF URLs."""

from __future__ import annotations

import logging

import httpx

from papermind.discovery.base import PaperResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openalex.org/works"


class OpenAlexProvider:
    """Search provider backed by the OpenAlex API.

    Free, no API key required. Polite pool (faster) with an email in
    the User-Agent header.

    Args:
        email: Contact email for the polite pool (higher rate limits).
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self, email: str = "papermind@users.noreply", timeout: float = 10.0
    ) -> None:
        self._email = email
        self._timeout = timeout

    @property
    def name(self) -> str:
        """Provider name."""
        return "openalex"

    async def search(self, query: str, *, limit: int = 10) -> list[PaperResult]:
        """Search OpenAlex for papers matching *query*.

        Args:
            query: Free-text search query.
            limit: Maximum number of results.

        Returns:
            List of PaperResult objects. Empty list on error.
        """
        params = {
            "search": query,
            "per_page": min(limit, 50),
            "select": "id,title,doi,authorships,publication_year,"
            "open_access,primary_location,cited_by_count,"
            "primary_topic,abstract_inverted_index",
        }
        headers = {
            "User-Agent": f"papermind/0.1 (mailto:{self._email})",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True
            ) as client:
                response = await client.get(_BASE_URL, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "OpenAlex API error %s: %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return []
        except httpx.RequestError as exc:
            logger.warning("OpenAlex request failed: %s", exc)
            return []

        works = data.get("results", [])
        return [self._parse(w) for w in works]

    def _parse(self, raw: dict) -> PaperResult:
        """Parse an OpenAlex work into a PaperResult."""
        # Authors
        authors = []
        for authorship in raw.get("authorships", []):
            name = authorship.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        # DOI — OpenAlex returns full URL like https://doi.org/10.xxxx/...
        doi_url = raw.get("doi", "") or ""
        doi = doi_url.replace("https://doi.org/", "").replace("http://doi.org/", "")

        # PDF URL — check primary_location and open_access
        oa = raw.get("open_access", {}) or {}
        loc = raw.get("primary_location", {}) or {}
        pdf_url = loc.get("pdf_url", "") or oa.get("oa_url", "") or ""

        # Venue from primary_location source
        source = loc.get("source", {}) or {}
        venue = source.get("display_name", "") or ""

        # Abstract — OpenAlex stores as inverted index {"word": [pos, ...]}
        abstract_index = raw.get("abstract_inverted_index") or {}
        if abstract_index:
            pairs: list[tuple[int, str]] = []
            for word, positions in abstract_index.items():
                for pos in positions:
                    pairs.append((pos, word))
            pairs.sort()
            abstract = " ".join(word for _, word in pairs)
        else:
            abstract = ""

        return PaperResult(
            title=raw.get("title", "") or "",
            authors=authors,
            year=raw.get("publication_year"),
            doi=doi,
            abstract=abstract,
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=bool(oa.get("is_oa", False)),
            venue=venue,
            citation_count=raw.get("cited_by_count", 0) or 0,
        )
