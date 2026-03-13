"""Paper discovery subsystem — search providers and orchestrator."""

from hydrofound.discovery.base import PaperResult, SearchProvider
from hydrofound.discovery.exa import ExaProvider
from hydrofound.discovery.orchestrator import discover_papers
from hydrofound.discovery.semantic_scholar import SemanticScholarProvider

__all__ = [
    "ExaProvider",
    "PaperResult",
    "SearchProvider",
    "SemanticScholarProvider",
    "discover_papers",
]
