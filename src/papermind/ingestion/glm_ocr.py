"""PDF → markdown conversion via GLM-OCR (zai-org/GLM-OCR).

Uses HuggingFace transformers to run the 0.9B-parameter GLM-OCR model locally.
PDF pages are rendered to images via pymupdf, then processed through the model
one page at a time to produce markdown output.

Requires: ``pip install papermind[ocr]`` (transformers, torch, pymupdf).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Module-level singleton — loaded once, reused across calls.
_model = None
_processor = None


def is_available() -> bool:
    """Check whether GLM-OCR dependencies are installed."""
    try:
        import fitz  # noqa: F401 — pymupdf
        import torch  # noqa: F401
        import transformers  # noqa: F401

        return True
    except ImportError:
        return False


def _ensure_model(model_name: str) -> tuple:
    """Load or return the cached model and processor.

    Args:
        model_name: HuggingFace model ID (e.g. ``zai-org/GLM-OCR``).

    Returns:
        Tuple of (processor, model).
    """
    global _model, _processor  # noqa: PLW0603

    if _model is not None and _processor is not None:
        return _processor, _model

    import os
    import warnings

    from transformers import AutoModelForImageTextToText, AutoProcessor

    # Suppress noisy HF warnings during model loading
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "0")
    warnings.filterwarnings("ignore", message=".*use_fast.*")
    warnings.filterwarnings("ignore", message=".*unauthenticated.*")

    logger.info("Loading GLM-OCR model: %s", model_name)
    try:
        _processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
    except (ValueError, KeyError, OSError) as exc:
        import transformers

        raise ImportError(
            f"GLM-OCR model requires transformers dev branch. "
            f"Installed: {transformers.__version__}. "
            f"Install with: pip install 'transformers @ "
            f"git+https://github.com/huggingface/transformers.git'"
        ) from exc
    _model = AutoModelForImageTextToText.from_pretrained(
        model_name,
        torch_dtype="auto",
        device_map="auto",
        trust_remote_code=True,
    )
    logger.info("GLM-OCR model loaded on %s", _model.device)
    return _processor, _model


def _render_pdf_pages(pdf_path: Path, dpi: int = 150) -> list:
    """Render each page of a PDF to a PIL Image.

    Args:
        pdf_path: Path to the PDF file.
        dpi: Resolution for rendering. 150 balances quality and memory.

    Returns:
        List of PIL Image objects, one per page.
    """
    import fitz  # pymupdf
    from PIL import Image

    doc = fitz.open(pdf_path)
    images = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for page in doc:
        pix = page.get_pixmap(matrix=matrix)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        images.append(img)

    doc.close()
    return images


def _ocr_image(image, processor, model) -> str:
    """Run GLM-OCR on a single image and return markdown text.

    Args:
        image: PIL Image of a document page.
        processor: HuggingFace processor for the model.
        model: The loaded GLM-OCR model.

    Returns:
        Markdown string for this page.
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "Text Recognition:"},
            ],
        }
    ]

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    ).to(model.device)

    inputs.pop("token_type_ids", None)

    generated_ids = model.generate(**inputs, max_new_tokens=8192)
    output_text = processor.decode(
        generated_ids[0][inputs["input_ids"].shape[1] :],
        skip_special_tokens=True,
    )
    return output_text.strip()


def extract_images(pdf_path: Path, output_dir: Path) -> list[str]:
    """Extract embedded images from a PDF and save them to output_dir.

    Args:
        pdf_path: Path to the PDF file.
        output_dir: Directory to save extracted images.

    Returns:
        List of saved image filenames (relative to output_dir).
    """
    import fitz  # pymupdf

    doc = fitz.open(pdf_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    img_counter = 0

    for page_num, page in enumerate(doc):
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            if base_image is None:
                continue

            img_bytes = base_image["image"]
            ext = base_image.get("ext", "png")

            # Skip tiny images (icons, bullets, etc.)
            if len(img_bytes) < 5000:
                continue

            img_counter += 1
            filename = f"figure_{img_counter}.{ext}"
            (output_dir / filename).write_bytes(img_bytes)
            saved.append(filename)
            logger.debug(
                "Extracted image: %s (page %d, %d bytes)",
                filename,
                page_num + 1,
                len(img_bytes),
            )

    doc.close()
    logger.info("Extracted %d image(s) from %s", len(saved), pdf_path.name)
    return saved


def _add_markdown_headings(text: str) -> str:
    """Post-process OCR output to add markdown headings.

    Detects likely section headings (numbered sections like "1 Introduction",
    "2.1 Methods", or short ALL-CAPS lines like "ABSTRACT") and adds
    appropriate ``#`` markers.

    Args:
        text: Raw OCR markdown text.

    Returns:
        Text with ``#`` headings added where detected.
    """
    lines = text.split("\n")
    result = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue

        # Already a heading
        if stripped.startswith("#"):
            result.append(line)
            continue

        # Numbered section: "1 Introduction", "2.1 Study area", "A.1 Appendix"
        if (
            re.match(
                r"^[A-Z]?\d+\.?\d*\s+[A-Z][A-Za-z]",
                stripped,
            )
            and len(stripped) < 100
        ):
            # Top-level (1, 2, 3) → ##, sub-section (2.1) → ###
            if re.match(r"^\d+\s", stripped):
                result.append(f"## {stripped}")
            else:
                result.append(f"### {stripped}")
            continue

        # ALL-CAPS short lines: ABSTRACT, INTRODUCTION, REFERENCES, etc.
        if (
            stripped.isupper()
            and len(stripped) > 3
            and len(stripped) < 60
            and stripped.replace(" ", "").isalpha()
        ):
            result.append(f"## {stripped.title()}")
            continue

        result.append(line)

    return "\n".join(result)


def convert_pdf_glm(
    path: Path,
    model_name: str = "zai-org/GLM-OCR",
    dpi: int = 150,
) -> str:
    """Convert a PDF file to markdown using GLM-OCR.

    Renders each page to an image, runs OCR, and concatenates the results
    with page break markers.

    Args:
        path: Path to the PDF file.
        model_name: HuggingFace model ID for GLM-OCR.
        dpi: Resolution for PDF page rendering.

    Returns:
        Concatenated markdown string for all pages.

    Raises:
        ImportError: If OCR dependencies are not installed.
        RuntimeError: If model loading or inference fails.
    """
    if not is_available():
        raise ImportError(
            "GLM-OCR requires extra dependencies. "
            "Install them with: pip install papermind[ocr]"
        )

    processor, model = _ensure_model(model_name)
    images = _render_pdf_pages(path, dpi=dpi)

    from rich.progress import Progress

    pages_md = []
    with Progress(transient=True) as progress:
        task = progress.add_task(f"OCR {path.name}", total=len(images))
        for img in images:
            page_text = _ocr_image(img, processor, model)
            pages_md.append(page_text)
            progress.advance(task)

    markdown = "\n\n---\n\n".join(pages_md)
    return _add_markdown_headings(markdown)
