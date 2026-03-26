"""Remote Z.AI OCR backend for PDF-to-Markdown conversion."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://api.z.ai/api/paas/v4"
DEFAULT_MODEL = "glm-ocr"


def convert_pdf_zai(
    path: Path,
    *,
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 120,
    max_pages: int = 40,
) -> str:
    """Convert a PDF file to markdown using the Z.AI layout parsing API."""
    if not api_key:
        raise RuntimeError(
            "Z.AI OCR requires PAPERMIND_ZAI_API_KEY or [apis].zai_api_key"
        )

    file_bytes = path.read_bytes()
    if len(file_bytes) > 50 * 1024 * 1024:
        raise RuntimeError(
            f"PDF exceeds Z.AI size limit (50MB): {path.name} "
            f"({len(file_bytes)} bytes)"
        )

    payload: dict[str, object] = {
        "model": model,
        "file": base64.b64encode(file_bytes).decode("ascii"),
        "request_id": f"papermind-{uuid.uuid4().hex}",
    }
    if max_pages > 0:
        payload["start_page_id"] = 1
        payload["end_page_id"] = max_pages

    url = f"{base_url.rstrip('/')}/layout_parsing"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        response = httpx.post(
            url,
            json=payload,
            headers=headers,
            timeout=timeout_seconds or None,
        )
    except httpx.HTTPStatusError as exc:
        detail = _safe_error_detail(exc.response)
        raise RuntimeError(f"Z.AI OCR request failed: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Z.AI OCR request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = _safe_error_detail(response)
        raise RuntimeError(f"Z.AI OCR request failed: {detail}")

    data = response.json()
    markdown = data.get("md_results")
    if not isinstance(markdown, str) or not markdown.strip():
        raise RuntimeError("Z.AI OCR response did not contain markdown output")
    return markdown


def _safe_error_detail(response: httpx.Response) -> str:
    """Extract a short error detail from a failed Z.AI response."""
    try:
        payload = response.json()
    except ValueError:
        return f"status={response.status_code}"

    if isinstance(payload, dict):
        for key in ("message", "msg", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return f"status={response.status_code} {value}"

    return f"status={response.status_code}"
