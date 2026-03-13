"""Paper download — direct HTTP + optional Playwright fallback.

Playwright integration is not yet implemented; a TODO marks the entry point
for that path.  The primary path uses httpx for direct HTTP downloads.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from hydrofound.discovery.base import PaperResult

# PDF magic bytes
_PDF_MAGIC = b"%PDF-"


def rewrite_arxiv_url(url: str) -> str:
    """Convert an arXiv abstract URL to a direct PDF URL.

    Args:
        url: Any URL — non-arXiv URLs are returned unchanged.

    Returns:
        Direct PDF URL for arXiv papers, original URL otherwise.

    Examples:
        >>> rewrite_arxiv_url("https://arxiv.org/abs/2301.12345")
        'https://arxiv.org/pdf/2301.12345.pdf'
        >>> rewrite_arxiv_url("https://arxiv.org/pdf/2301.12345")
        'https://arxiv.org/pdf/2301.12345.pdf'
    """
    url = re.sub(r"arxiv\.org/abs/", "arxiv.org/pdf/", url)
    if "arxiv.org/pdf/" in url and not url.endswith(".pdf"):
        url += ".pdf"
    return url


def _is_valid_pdf(content: bytes) -> bool:
    """Check PDF magic bytes.

    Args:
        content: Raw bytes of the downloaded file.

    Returns:
        True if the content begins with ``%PDF-``.
    """
    return content[:5] == _PDF_MAGIC


async def download_paper(
    result: PaperResult,
    output_dir: Path,
    *,
    timeout: int = 60,
) -> Path | None:
    """Download a paper PDF via direct HTTP.

    Rewrites arXiv abstract URLs to direct PDF URLs before fetching.
    Validates the response with a magic-bytes check — non-PDF responses
    (e.g., HTML paywalls) are discarded.

    TODO: add Playwright fallback for sites that require JS rendering or
    cookie consent (e.g., ScienceDirect, Springer).  The caller should
    pass ``playwright=True`` to opt in.

    Args:
        result: PaperResult with a ``pdf_url`` field.
        output_dir: Directory to write the downloaded file into.  Created
            if it does not exist.
        timeout: HTTP request timeout in seconds.

    Returns:
        Path to the saved PDF, or ``None`` if the download failed.
    """
    if not result.pdf_url:
        return None

    url = result.pdf_url
    if "arxiv.org" in url:
        url = rewrite_arxiv_url(url)

    output_dir.mkdir(parents=True, exist_ok=True)

    from hydrofound.ingestion.common import slugify

    name = slugify(result.title or result.doi or "paper")[:80]
    dest = output_dir / f"{name}.pdf"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=timeout)
            resp.raise_for_status()

        content = resp.content
        if not _is_valid_pdf(content):
            return None

        dest.write_bytes(content)
        return dest
    except Exception:  # noqa: BLE001
        return None


def load_last_search(kb_path: Path) -> list[PaperResult]:
    """Load cached search results from ``kb/.hydrofound/last_search.json``.

    The cache is written by ``hydrofound discover``.  Returns an empty list
    if the cache file does not exist.

    Args:
        kb_path: Root path of the knowledge base.

    Returns:
        List of :class:`PaperResult` objects from the most recent search.
    """
    cache_path = kb_path / ".hydrofound" / "last_search.json"
    if not cache_path.exists():
        return []

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    raw_results = data.get("results", data) if isinstance(data, dict) else data
    if not isinstance(raw_results, list):
        return []

    return [
        PaperResult(
            title=d.get("title", ""),
            authors=d.get("authors", []),
            year=d.get("year"),
            doi=d.get("doi", ""),
            abstract=d.get("abstract", ""),
            pdf_url=d.get("pdf_url", ""),
            source=d.get("source", ""),
            is_open_access=d.get("is_open_access", False),
            venue=d.get("venue", ""),
            citation_count=d.get("citation_count", 0),
        )
        for d in raw_results
        if isinstance(d, dict)
    ]


def pick_results(results: list[PaperResult], indices: str) -> list[PaperResult]:
    """Select results by 1-based index string.

    Silently skips out-of-range indices rather than raising.

    Args:
        results: Full list of :class:`PaperResult` objects.
        indices: Comma-separated 1-based indices, e.g. ``"1,3,5"``.

    Returns:
        Subset of *results* at the requested positions.
    """
    picked: list[PaperResult] = []
    for idx_str in indices.split(","):
        stripped = idx_str.strip()
        if not stripped:
            continue
        try:
            idx = int(stripped) - 1
        except ValueError:
            continue
        if 0 <= idx < len(results):
            picked.append(results[idx])
    return picked
