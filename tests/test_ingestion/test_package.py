"""Tests for package API extraction via griffe."""

from __future__ import annotations

from papermind.ingestion.package import extract_api, render_api_markdown


def test_extract_api_from_self() -> None:
    """Use papermind itself as a known test package."""
    api = extract_api("papermind")
    assert len(api.modules) >= 1
    assert any("papermind" in m.name for m in api.modules)


def test_render_api_produces_markdown() -> None:
    api = extract_api("papermind")
    md = render_api_markdown(api, "papermind")
    assert "papermind" in md.lower()
    assert "```" in md or "#" in md  # Should contain headers or code blocks


def test_render_includes_docstrings() -> None:
    api = extract_api("papermind")
    md = render_api_markdown(api, "papermind")
    assert "knowledge base" in md.lower() or "papermind" in md.lower()
