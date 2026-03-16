"""Shared provider builder for paper discovery."""

from __future__ import annotations

from hydrofound.config import HydroFoundConfig
from hydrofound.discovery.base import SearchProvider


def build_providers(
    source: str,
    config: HydroFoundConfig,
) -> list[SearchProvider]:
    """Build provider list based on source flag and available API keys.

    Args:
        source: One of ``"all"``, ``"openalex"``, ``"semantic_scholar"``, or ``"exa"``.
        config: HydroFoundConfig instance.

    Returns:
        List of instantiated provider objects.
    """
    from hydrofound.discovery.exa import ExaProvider
    from hydrofound.discovery.openalex import OpenAlexProvider
    from hydrofound.discovery.semantic_scholar import SemanticScholarProvider

    want_oa = source in ("all", "openalex")
    want_ss = source in ("all", "semantic_scholar")
    want_exa = source in ("all", "exa")

    providers: list[SearchProvider] = []

    if want_oa:
        providers.append(OpenAlexProvider())

    if want_ss:
        providers.append(SemanticScholarProvider(api_key=config.semantic_scholar_key))

    if want_exa and config.exa_key:
        providers.append(ExaProvider(api_key=config.exa_key))

    return providers
