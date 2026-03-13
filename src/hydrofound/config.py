"""Configuration loading with env var overrides."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HydroFoundConfig:
    """HydroFound configuration."""

    base_path: Path

    # Search
    qmd_path: str = "qmd"
    node_path: str = "node"
    fallback_search: bool = True

    # APIs (env vars take precedence)
    semantic_scholar_key: str = ""
    exa_key: str = ""
    firecrawl_key: str = ""

    # Ingestion
    marker_path: str = "marker"
    marker_use_llm: bool = False
    default_paper_topic: str = "uncategorized"

    # Privacy
    offline_only: bool = False


def load_config(base_path: Path) -> HydroFoundConfig:
    """Load config from .hydrofound/config.toml with env var overrides.

    Args:
        base_path: Root of the HydroFound knowledge base.

    Returns:
        Populated config object.
    """
    cfg = HydroFoundConfig(base_path=base_path)

    # Load from TOML if it exists
    config_file = base_path / ".hydrofound" / "config.toml"
    if config_file.exists():
        with open(config_file, "rb") as f:
            data = tomllib.load(f)

        search = data.get("search", {})
        cfg.qmd_path = search.get("qmd_path", cfg.qmd_path)
        cfg.node_path = search.get("node_path", cfg.node_path)
        cfg.fallback_search = search.get("fallback_search", cfg.fallback_search)

        apis = data.get("apis", {})
        cfg.semantic_scholar_key = apis.get(
            "semantic_scholar_key", cfg.semantic_scholar_key
        )
        cfg.exa_key = apis.get("exa_key", cfg.exa_key)

        ingestion = data.get("ingestion", {})
        cfg.marker_path = ingestion.get("marker_path", cfg.marker_path)
        cfg.marker_use_llm = ingestion.get("marker_use_llm", cfg.marker_use_llm)
        cfg.default_paper_topic = ingestion.get(
            "default_paper_topic", cfg.default_paper_topic
        )

        firecrawl = data.get("firecrawl", {})
        cfg.firecrawl_key = firecrawl.get("api_key", cfg.firecrawl_key)

        privacy = data.get("privacy", {})
        cfg.offline_only = privacy.get("offline_only", cfg.offline_only)

    # Env vars override everything
    cfg.semantic_scholar_key = os.environ.get(
        "HYDROFOUND_SEMANTIC_SCHOLAR_KEY", cfg.semantic_scholar_key
    )
    cfg.exa_key = os.environ.get("HYDROFOUND_EXA_KEY", cfg.exa_key)
    cfg.firecrawl_key = os.environ.get("HYDROFOUND_FIRECRAWL_KEY", cfg.firecrawl_key)

    return cfg
