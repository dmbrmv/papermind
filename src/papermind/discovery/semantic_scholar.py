"""Semantic Scholar Graph API search provider."""

from __future__ import annotations

import logging

import httpx

from papermind.discovery.base import PaperResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_DETAIL_URL = "https://api.semanticscholar.org/graph/v1/paper"
_FIELDS = (
    "title,authors,year,abstract,externalIds,"
    "isOpenAccess,venue,citationCount,openAccessPdf,"
    "references,citations"
)
_REF_FIELDS = "externalIds"


class SemanticScholarProvider:
    """Search provider backed by the Semantic Scholar Graph API.

    Args:
        api_key: Optional API key sent as ``x-api-key`` header.
            Raises the rate limit from 100 req/5min to 1 req/sec.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str = "",
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout

    @property
    def name(self) -> str:
        """Provider name."""
        return "semantic_scholar"

    async def search(self, query: str, *, limit: int = 10) -> list[PaperResult]:
        """Search Semantic Scholar for papers matching *query*.

        Args:
            query: Free-text search query.
            limit: Maximum number of results to return (capped at 100 by API).

        Returns:
            List of :class:`PaperResult` objects.  Returns an empty list on
            any HTTP or API error rather than raising.
        """
        params: dict[str, str | int] = {
            "query": query,
            "limit": limit,
            "fields": _FIELDS,
        }
        headers: dict[str, str] = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(_BASE_URL, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Semantic Scholar API error %s: %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return []
        except httpx.RequestError as exc:
            logger.warning("Semantic Scholar request failed: %s", exc)
            return []

        papers = data.get("data", [])
        return [self._parse(paper) for paper in papers]

    def _parse(self, raw: dict) -> PaperResult:
        """Parse a single Semantic Scholar paper record into a PaperResult.

        Args:
            raw: Raw dict from the API ``data`` array.

        Returns:
            Populated :class:`PaperResult`.
        """
        authors = [a.get("name", "") for a in raw.get("authors", []) if a.get("name")]
        external_ids = raw.get("externalIds") or {}
        doi = external_ids.get("DOI", "")

        open_access_pdf = raw.get("openAccessPdf") or {}
        pdf_url = open_access_pdf.get("url", "")

        cites = self._extract_dois(raw.get("references") or [])
        cited_by = self._extract_dois(raw.get("citations") or [])

        return PaperResult(
            title=raw.get("title", ""),
            authors=authors,
            year=raw.get("year"),
            doi=doi,
            abstract=raw.get("abstract", "") or "",
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=bool(raw.get("isOpenAccess", False)),
            venue=raw.get("venue", "") or "",
            citation_count=raw.get("citationCount", 0) or 0,
            cites=cites,
            cited_by=cited_by,
        )

    @staticmethod
    def _extract_dois(refs: list[dict]) -> list[str]:
        """Extract DOIs from Semantic Scholar reference/citation entries.

        Args:
            refs: List of reference dicts from the API, each with optional
                ``externalIds`` containing a ``DOI`` key.

        Returns:
            List of DOI strings (empty entries filtered out).
        """
        dois: list[str] = []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            ext = ref.get("externalIds") or {}
            doi = ext.get("DOI", "")
            if doi:
                dois.append(doi)
        return dois


async def lookup_citations_by_doi(
    doi: str,
    api_key: str = "",
    timeout: float = 10.0,
) -> tuple[list[str], list[str]]:
    """Look up citation data for a single paper by DOI.

    Uses the Semantic Scholar single-paper detail endpoint which
    returns full reference/citation data (unlike the search endpoint).

    Args:
        doi: DOI string (e.g. ``10.1002/hyp.14561``).
        api_key: Optional SS API key for higher rate limits.
        timeout: HTTP timeout in seconds.

    Returns:
        Tuple of (cites, cited_by) — each a list of DOI strings.
        Returns ([], []) on any error.
    """
    if not doi:
        return [], []

    url = f"{_DETAIL_URL}/DOI:{doi}"
    params = {"fields": "references.externalIds,citations.externalIds"}
    headers: dict[str, str] = {}
    if api_key:
        headers["x-api-key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                logger.debug("SS detail %s: HTTP %s", doi, resp.status_code)
                return [], []
            data = resp.json()
    except (httpx.RequestError, Exception) as exc:
        logger.debug("SS detail error for %s: %s", doi, exc)
        return [], []

    cites = SemanticScholarProvider._extract_dois(data.get("references") or [])
    cited_by = SemanticScholarProvider._extract_dois(data.get("citations") or [])
    return cites, cited_by
