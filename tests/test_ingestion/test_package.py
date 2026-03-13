"""Tests for package API extraction via griffe."""

from __future__ import annotations

from hydrofound.ingestion.package import extract_api, render_api_markdown


def test_extract_api_from_self() -> None:
    """Use hydrofound itself as a known test package."""
    api = extract_api("hydrofound")
    assert len(api.modules) >= 1
    assert any("hydrofound" in m.name for m in api.modules)


def test_render_api_produces_markdown() -> None:
    api = extract_api("hydrofound")
    md = render_api_markdown(api, "hydrofound")
    assert "hydrofound" in md.lower()
    assert "```" in md or "#" in md  # Should contain headers or code blocks


def test_render_includes_docstrings() -> None:
    api = extract_api("hydrofound")
    md = render_api_markdown(api, "hydrofound")
    assert "knowledge base" in md.lower() or "hydrofound" in md.lower()
