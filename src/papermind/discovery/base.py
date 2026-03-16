"""Base protocol and data types for paper search providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class PaperResult:
    """A paper found via search."""

    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str = ""
    abstract: str = ""
    pdf_url: str = ""
    source: str = ""  # "semantic_scholar", "exa", etc.
    is_open_access: bool = False
    venue: str = ""
    citation_count: int = 0
    cites: list[str] = field(default_factory=list)  # DOIs of referenced papers
    cited_by: list[str] = field(default_factory=list)  # DOIs of citing papers


class SearchProvider(Protocol):
    """Protocol for paper search providers."""

    async def search(self, query: str, *, limit: int = 10) -> list[PaperResult]:
        """Search for papers matching the query.

        Args:
            query: Free-text search query.
            limit: Maximum number of results to return.

        Returns:
            List of matching paper results.
        """
        ...

    @property
    def name(self) -> str:
        """Provider name."""
        ...
