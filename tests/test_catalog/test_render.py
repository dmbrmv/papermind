"""Tests for catalog.md rendering."""

from __future__ import annotations

from papermind.catalog.index import CatalogEntry
from papermind.catalog.render import render_catalog_md


def test_empty_catalog() -> None:
    md = render_catalog_md([])
    assert "0 papers" in md
    assert "0 packages" in md


def test_papers_grouped_by_topic() -> None:
    entries = [
        CatalogEntry(
            id="p1",
            type="paper",
            path="papers/hydrology/a.md",
            title="Paper A",
            topic="hydrology",
            added="2026-01-01",
        ),
        CatalogEntry(
            id="p2",
            type="paper",
            path="papers/ml/b.md",
            title="Paper B",
            topic="machine-learning",
            added="2026-01-02",
        ),
    ]
    md = render_catalog_md(entries)
    assert "### Hydrology (1)" in md
    assert "### Machine-Learning (1)" in md
    assert "[Paper A]" in md
    assert "[Paper B]" in md


def test_packages_listed() -> None:
    entries = [
        CatalogEntry(
            id="pkg1",
            type="package",
            path="packages/xarray/_index.md",
            title="xarray",
            files=["api.md", "guides.md"],
        ),
    ]
    md = render_catalog_md(entries)
    assert "xarray" in md
    assert "2 files" in md
