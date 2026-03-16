"""Configuration loading with env var overrides."""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Known top-level sections in config.toml
_KNOWN_SECTIONS = {"search", "apis", "ingestion", "firecrawl", "privacy"}


@dataclass
class PaperMindConfig:
    """PaperMind configuration."""

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
    ocr_model: str = "zai-org/GLM-OCR"
    ocr_dpi: int = 150
    default_paper_topic: str = "uncategorized"

    # Privacy
    offline_only: bool = False


def load_config(base_path: Path) -> PaperMindConfig:
    """Load config from .papermind/config.toml with env var overrides.

    Args:
        base_path: Root of the PaperMind knowledge base.

    Returns:
        Populated config object.
    """
    cfg = PaperMindConfig(base_path=base_path)

    # Load from TOML if it exists
    config_file = base_path / ".papermind" / "config.toml"
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
        cfg.ocr_model = ingestion.get("ocr_model", cfg.ocr_model)
        cfg.ocr_dpi = ingestion.get("ocr_dpi", cfg.ocr_dpi)
        cfg.default_paper_topic = ingestion.get(
            "default_paper_topic", cfg.default_paper_topic
        )

        firecrawl = data.get("firecrawl", {})
        cfg.firecrawl_key = firecrawl.get("api_key", cfg.firecrawl_key)

        privacy = data.get("privacy", {})
        cfg.offline_only = privacy.get("offline_only", cfg.offline_only)

        # Warn on unknown top-level sections
        unknown = set(data.keys()) - _KNOWN_SECTIONS
        for section in sorted(unknown):
            logger.warning(
                "config.toml: unknown section [%s] — will be ignored", section
            )

        # Clamp ocr_dpi to [72, 600]
        if cfg.ocr_dpi < 72:
            logger.warning(
                "config.toml: ocr_dpi=%d is below minimum (72) — clamped to 72",
                cfg.ocr_dpi,
            )
            cfg.ocr_dpi = 72
        elif cfg.ocr_dpi > 600:
            logger.warning(
                "config.toml: ocr_dpi=%d exceeds maximum (600) — clamped to 600",
                cfg.ocr_dpi,
            )
            cfg.ocr_dpi = 600

    # Env vars override everything
    cfg.semantic_scholar_key = os.environ.get(
        "PAPERMIND_SEMANTIC_SCHOLAR_KEY", cfg.semantic_scholar_key
    )
    cfg.exa_key = os.environ.get("PAPERMIND_EXA_KEY", cfg.exa_key)
    cfg.firecrawl_key = os.environ.get("PAPERMIND_FIRECRAWL_KEY", cfg.firecrawl_key)

    return cfg
