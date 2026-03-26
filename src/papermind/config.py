"""Configuration loading with env var overrides."""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import replace
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
    zai_api_key: str = ""

    # Ingestion
    ocr_backend: str = "local"
    ocr_model: str = "zai-org/GLM-OCR"
    ocr_dpi: int = 150
    ocr_max_new_tokens: int = 4096
    extract_pdf_images: bool = True
    default_paper_topic: str = "uncategorized"
    recovery_ocr_dpi: int = 120
    recovery_ocr_max_new_tokens: int = 3072
    recovery_max_pdf_pages: int = 20
    recovery_ocr_timeout_seconds: int = 180
    zai_base_url: str = "https://api.z.ai/api/paas/v4"
    zai_model: str = "glm-ocr"
    zai_timeout_seconds: int = 120
    zai_max_pages: int = 40

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
        cfg.zai_api_key = apis.get("zai_api_key", cfg.zai_api_key)

        ingestion = data.get("ingestion", {})
        cfg.ocr_backend = ingestion.get("ocr_backend", cfg.ocr_backend)
        cfg.ocr_model = ingestion.get("ocr_model", cfg.ocr_model)
        cfg.ocr_dpi = ingestion.get("ocr_dpi", cfg.ocr_dpi)
        cfg.ocr_max_new_tokens = ingestion.get(
            "ocr_max_new_tokens", cfg.ocr_max_new_tokens
        )
        cfg.extract_pdf_images = ingestion.get(
            "extract_pdf_images", cfg.extract_pdf_images
        )
        cfg.default_paper_topic = ingestion.get(
            "default_paper_topic", cfg.default_paper_topic
        )
        cfg.recovery_ocr_dpi = ingestion.get(
            "recovery_ocr_dpi", cfg.recovery_ocr_dpi
        )
        cfg.recovery_ocr_max_new_tokens = ingestion.get(
            "recovery_ocr_max_new_tokens", cfg.recovery_ocr_max_new_tokens
        )
        cfg.recovery_max_pdf_pages = ingestion.get(
            "recovery_max_pdf_pages", cfg.recovery_max_pdf_pages
        )
        cfg.recovery_ocr_timeout_seconds = ingestion.get(
            "recovery_ocr_timeout_seconds", cfg.recovery_ocr_timeout_seconds
        )
        cfg.zai_base_url = ingestion.get("zai_base_url", cfg.zai_base_url)
        cfg.zai_model = ingestion.get("zai_model", cfg.zai_model)
        cfg.zai_timeout_seconds = ingestion.get(
            "zai_timeout_seconds", cfg.zai_timeout_seconds
        )
        cfg.zai_max_pages = ingestion.get("zai_max_pages", cfg.zai_max_pages)

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

        if cfg.recovery_ocr_dpi < 72:
            logger.warning(
                "config.toml: recovery_ocr_dpi=%d is below minimum (72) — clamped to 72",
                cfg.recovery_ocr_dpi,
            )
            cfg.recovery_ocr_dpi = 72
        elif cfg.recovery_ocr_dpi > 600:
            logger.warning(
                "config.toml: recovery_ocr_dpi=%d exceeds maximum (600) — clamped to 600",
                cfg.recovery_ocr_dpi,
            )
            cfg.recovery_ocr_dpi = 600

        if cfg.recovery_max_pdf_pages < 0:
            logger.warning(
                "config.toml: recovery_max_pdf_pages=%d is below minimum (0) — clamped to 0",
                cfg.recovery_max_pdf_pages,
            )
            cfg.recovery_max_pdf_pages = 0

        if cfg.recovery_ocr_timeout_seconds < 0:
            logger.warning(
                "config.toml: recovery_ocr_timeout_seconds=%d is below minimum (0) — clamped to 0",
                cfg.recovery_ocr_timeout_seconds,
            )
            cfg.recovery_ocr_timeout_seconds = 0

        if cfg.ocr_max_new_tokens < 1:
            logger.warning(
                "config.toml: ocr_max_new_tokens=%d is below minimum (1) — clamped to 1",
                cfg.ocr_max_new_tokens,
            )
            cfg.ocr_max_new_tokens = 1

        if cfg.recovery_ocr_max_new_tokens < 1:
            logger.warning(
                "config.toml: recovery_ocr_max_new_tokens=%d is below minimum (1) — clamped to 1",
                cfg.recovery_ocr_max_new_tokens,
            )
            cfg.recovery_ocr_max_new_tokens = 1

        if cfg.ocr_backend not in {"local", "zai"}:
            logger.warning(
                "config.toml: ocr_backend=%r is invalid — defaulting to 'local'",
                cfg.ocr_backend,
            )
            cfg.ocr_backend = "local"

        if cfg.zai_timeout_seconds < 0:
            logger.warning(
                "config.toml: zai_timeout_seconds=%d is below minimum (0) — clamped to 0",
                cfg.zai_timeout_seconds,
            )
            cfg.zai_timeout_seconds = 0

        if cfg.zai_max_pages < 0:
            logger.warning(
                "config.toml: zai_max_pages=%d is below minimum (0) — clamped to 0",
                cfg.zai_max_pages,
            )
            cfg.zai_max_pages = 0

    # Env vars override everything
    cfg.semantic_scholar_key = os.environ.get(
        "PAPERMIND_SEMANTIC_SCHOLAR_KEY", cfg.semantic_scholar_key
    )
    cfg.exa_key = os.environ.get("PAPERMIND_EXA_KEY", cfg.exa_key)
    cfg.firecrawl_key = os.environ.get("PAPERMIND_FIRECRAWL_KEY", cfg.firecrawl_key)
    cfg.zai_api_key = os.environ.get("PAPERMIND_ZAI_API_KEY", cfg.zai_api_key)

    return cfg


def recovery_config(cfg: PaperMindConfig) -> PaperMindConfig:
    """Return a recovery-oriented config with bounded OCR defaults."""
    return replace(
        cfg,
        ocr_dpi=cfg.recovery_ocr_dpi,
        ocr_max_new_tokens=cfg.recovery_ocr_max_new_tokens,
    )
