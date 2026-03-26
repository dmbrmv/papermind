"""Tests for the remote Z.AI OCR backend."""

from __future__ import annotations
from pathlib import Path

import httpx
import pytest

from papermind.ingestion.zai_ocr import convert_pdf_zai

PDF_MAGIC = b"%PDF-1.4\n" + b"x" * 2048


def _make_pdf(path: Path) -> Path:
    path.write_bytes(PDF_MAGIC)
    return path


def test_convert_pdf_zai_returns_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _make_pdf(tmp_path / "paper.pdf")

    def fake_post(url: str, *, json: dict, headers: dict, timeout: int | None) -> httpx.Response:
        assert url.endswith("/layout_parsing")
        assert json["model"] == "glm-ocr"
        assert json["file"]
        assert headers["Authorization"] == "Bearer test-key"
        assert timeout == 30
        return httpx.Response(
            200,
            json={"md_results": "# Parsed Document\n\nBody text.\n"},
        )

    monkeypatch.setattr("papermind.ingestion.zai_ocr.httpx.post", fake_post)
    markdown = convert_pdf_zai(
        pdf,
        api_key="test-key",
        timeout_seconds=30,
        max_pages=12,
    )
    assert markdown == "# Parsed Document\n\nBody text.\n"


def test_convert_pdf_zai_missing_api_key_raises(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "paper.pdf")
    with pytest.raises(RuntimeError, match="PAPERMIND_ZAI_API_KEY"):
        convert_pdf_zai(pdf, api_key="")


def test_convert_pdf_zai_http_error_includes_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _make_pdf(tmp_path / "paper.pdf")

    def fake_post(url: str, *, json: dict, headers: dict, timeout: int | None) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(
            401,
            json={"message": "invalid api key"},
            request=request,
        )

    monkeypatch.setattr("papermind.ingestion.zai_ocr.httpx.post", fake_post)
    with pytest.raises(RuntimeError, match="status=401 invalid api key"):
        convert_pdf_zai(pdf, api_key="bad-key")


def test_convert_pdf_zai_missing_markdown_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _make_pdf(tmp_path / "paper.pdf")

    def fake_post(url: str, *, json: dict, headers: dict, timeout: int | None) -> httpx.Response:
        return httpx.Response(200, json={"id": "task_123"})

    monkeypatch.setattr("papermind.ingestion.zai_ocr.httpx.post", fake_post)
    with pytest.raises(RuntimeError, match="did not contain markdown output"):
        convert_pdf_zai(pdf, api_key="test-key")
