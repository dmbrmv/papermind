"""Unpaywall DOI → PDF URL resolver.

Free API, no key required. Given a DOI, returns the best open-access
PDF URL if one exists. Rate limit: 100k/day with polite email header.

See: https://unpaywall.org/products/api
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.unpaywall.org/v2"


async def resolve_pdf_url(
    doi: str,
    email: str = "hydrofound@users.noreply",
    timeout: float = 10.0,
) -> str | None:
    """Resolve a DOI to a direct PDF URL via Unpaywall.

    Args:
        doi: DOI string (e.g. ``10.1002/hyp.14561``).
        email: Contact email for Unpaywall polite pool.
        timeout: HTTP timeout in seconds.

    Returns:
        Direct PDF URL if found, None otherwise.
    """
    if not doi:
        return None

    url = f"{_BASE_URL}/{doi}"
    params = {"email": email}

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                logger.debug("Unpaywall %s: HTTP %s", doi, response.status_code)
                return None

            data = response.json()

        # Try best_oa_location first, then iterate oa_locations
        best = data.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf", "")

        if not pdf_url:
            for loc in data.get("oa_locations", []):
                pdf_url = loc.get("url_for_pdf", "")
                if pdf_url:
                    break

        if pdf_url:
            logger.debug("Unpaywall resolved %s → %s", doi, pdf_url)
            return pdf_url

        logger.debug("Unpaywall: no PDF for %s (is_oa=%s)", doi, data.get("is_oa"))
        return None

    except (httpx.RequestError, Exception) as exc:
        logger.debug("Unpaywall error for %s: %s", doi, exc)
        return None
