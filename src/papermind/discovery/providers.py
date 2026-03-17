"""Shared provider builder for paper discovery."""

from __future__ import annotations

from papermind.config import PaperMindConfig
from papermind.discovery.base import SearchProvider


def build_providers(
    source: str,
    config: PaperMindConfig,
) -> list[SearchProvider]:
    """Build provider list based on source flag and available API keys.

    Args:
        source: One of ``"all"``, ``"openalex"``, ``"semantic_scholar"``, or ``"exa"``.
        config: PaperMindConfig instance.

    Returns:
        List of instantiated provider objects.
    """
    from papermind.discovery.exa import ExaProvider
    from papermind.discovery.openalex import OpenAlexProvider

    want_oa = source in ("all", "openalex")
    want_ss = source == "semantic_scholar"  # only when explicitly requested
    want_exa = source in ("all", "exa")

    providers: list[SearchProvider] = []

    if want_oa:
        providers.append(OpenAlexProvider())

    if want_ss and config.semantic_scholar_key:
        from papermind.discovery.semantic_scholar import SemanticScholarProvider

        providers.append(SemanticScholarProvider(api_key=config.semantic_scholar_key))

    if want_exa and config.exa_key:
        providers.append(ExaProvider(api_key=config.exa_key))

    return providers
