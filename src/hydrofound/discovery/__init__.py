"""Paper discovery subsystem — search providers."""

from hydrofound.discovery.base import PaperResult, SearchProvider
from hydrofound.discovery.semantic_scholar import SemanticScholarProvider

__all__ = ["PaperResult", "SearchProvider", "SemanticScholarProvider"]
