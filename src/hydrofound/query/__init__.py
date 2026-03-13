"""hydrofound.query — search backends for the knowledge base."""

from __future__ import annotations

from hydrofound.query.fallback import SearchResult, fallback_search

__all__ = ["fallback_search", "SearchResult"]
