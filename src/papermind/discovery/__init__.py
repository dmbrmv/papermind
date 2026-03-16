"""Paper discovery subsystem — search providers and orchestrator."""

from papermind.discovery.base import PaperResult, SearchProvider
from papermind.discovery.exa import ExaProvider
from papermind.discovery.orchestrator import discover_papers
from papermind.discovery.semantic_scholar import SemanticScholarProvider

__all__ = [
    "ExaProvider",
    "PaperResult",
    "SearchProvider",
    "SemanticScholarProvider",
    "discover_papers",
]
