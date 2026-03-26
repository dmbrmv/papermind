"""OCR backend dispatch for paper ingestion."""

from __future__ import annotations

from pathlib import Path

from papermind.config import PaperMindConfig


def convert_pdf_with_backend(path: Path, config: PaperMindConfig) -> str:
    """Convert a PDF to markdown using the configured OCR backend."""
    backend = config.ocr_backend

    if backend == "local":
        from papermind.ingestion.glm_ocr import convert_pdf_glm

        return convert_pdf_glm(
            path,
            model_name=config.ocr_model,
            dpi=config.ocr_dpi,
            max_new_tokens=config.ocr_max_new_tokens,
        )

    if backend == "zai":
        if config.offline_only:
            raise RuntimeError("Z.AI OCR is unavailable in offline mode")

        from papermind.ingestion.zai_ocr import convert_pdf_zai

        return convert_pdf_zai(
            path,
            api_key=config.zai_api_key,
            base_url=config.zai_base_url,
            model=config.zai_model,
            timeout_seconds=config.zai_timeout_seconds,
            max_pages=config.zai_max_pages,
        )

    raise RuntimeError(f"Unsupported OCR backend: {backend}")
