"""Tests for catalog.json CRUD operations."""

from __future__ import annotations

from pathlib import Path

import pytest
from hydrofound.catalog.index import CatalogEntry, CatalogIndex


@pytest.fixture
def catalog(tmp_path: Path) -> CatalogIndex:
    (tmp_path / "catalog.json").write_text("[]")
    return CatalogIndex(tmp_path)


def test_add_entry(catalog: CatalogIndex) -> None:
    entry = CatalogEntry(
        id="paper-test-2024",
        type="paper",
        title="Test Paper",
        path="papers/hydrology/test-2024.md",
        topic="hydrology",
    )
    catalog.add(entry)
    assert len(catalog.entries) == 1
    assert catalog.entries[0].id == "paper-test-2024"


def test_add_persists_to_disk(catalog: CatalogIndex) -> None:
    entry = CatalogEntry(
        id="paper-test-2024",
        type="paper",
        title="Test Paper",
        path="papers/hydrology/test-2024.md",
    )
    catalog.add(entry)
    # Reload from disk
    fresh = CatalogIndex(catalog.base_path)
    assert len(fresh.entries) == 1


def test_remove_entry(catalog: CatalogIndex) -> None:
    entry = CatalogEntry(id="paper-test-2024", type="paper", path="papers/test.md")
    catalog.add(entry)
    removed = catalog.remove("paper-test-2024")
    assert removed is True
    assert len(catalog.entries) == 0


def test_remove_nonexistent_returns_false(catalog: CatalogIndex) -> None:
    assert catalog.remove("nonexistent") is False


def test_get_by_id(catalog: CatalogIndex) -> None:
    entry = CatalogEntry(id="paper-test-2024", type="paper", path="papers/test.md")
    catalog.add(entry)
    found = catalog.get("paper-test-2024")
    assert found is not None
    assert found.id == "paper-test-2024"


def test_has_duplicate_by_doi(catalog: CatalogIndex) -> None:
    entry = CatalogEntry(
        id="paper-test-2024",
        type="paper",
        path="papers/test.md",
        doi="10.1234/test",
    )
    catalog.add(entry)
    assert catalog.has_doi("10.1234/test") is True
    assert catalog.has_doi("10.1234/other") is False


def test_stats(catalog: CatalogIndex) -> None:
    catalog.add(
        CatalogEntry(id="p1", type="paper", path="papers/a/1.md", topic="hydrology")
    )
    catalog.add(
        CatalogEntry(id="p2", type="paper", path="papers/a/2.md", topic="hydrology")
    )
    catalog.add(CatalogEntry(id="pkg1", type="package", path="packages/x/_index.md"))
    stats = catalog.stats()
    assert stats["papers"] == 2
    assert stats["packages"] == 1
    assert stats["codebases"] == 0
    assert stats["topics"]["hydrology"] == 2


def test_rebuild_from_frontmatter(tmp_path: Path) -> None:
    """rebuild() reconstructs catalog from .md frontmatter."""
    import frontmatter

    (tmp_path / "catalog.json").write_text("[]")
    papers_dir = tmp_path / "papers" / "hydrology"
    papers_dir.mkdir(parents=True)

    post = frontmatter.Post("# Test Paper\n\nContent here.")
    post.metadata = {
        "id": "paper-test-2024",
        "type": "paper",
        "title": "Test Paper",
        "topic": "hydrology",
        "added": "2024-01-01",
    }
    (papers_dir / "test-2024.md").write_text(frontmatter.dumps(post))

    rebuilt = CatalogIndex.rebuild(tmp_path)
    assert len(rebuilt.entries) == 1
    assert rebuilt.entries[0].id == "paper-test-2024"
    assert rebuilt.entries[0].topic == "hydrology"
    # Verify persisted to disk
    fresh = CatalogIndex(tmp_path)
    assert len(fresh.entries) == 1
