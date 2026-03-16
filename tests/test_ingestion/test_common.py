"""Tests for frontmatter and path utilities."""

from __future__ import annotations

from pathlib import Path

from papermind.ingestion.common import build_frontmatter, generate_id, slugify


def test_slugify_basic() -> None:
    assert slugify("Green and Ampt Model") == "green-and-ampt-model"


def test_slugify_special_chars() -> None:
    assert slugify("A Review: SWAT+ (2021)") == "a-review-swat-2021"


def test_slugify_unicode() -> None:
    assert slugify("Müller et al.") == "muller-et-al"


def test_generate_paper_id() -> None:
    pid = generate_id("paper", "Green and Ampt Model", year=1911)
    assert pid == "paper-green-and-ampt-model-1911"


def test_generate_package_id() -> None:
    pid = generate_id("package", "xarray")
    assert pid == "package-xarray"


def test_generate_codebase_id() -> None:
    pid = generate_id("codebase", "swatplus")
    assert pid == "codebase-swatplus"


def test_generate_id_collision_detection(tmp_path: Path) -> None:
    """Collision detection appends -2, -3 etc."""
    import frontmatter

    papers_dir = tmp_path / "papers" / "hydrology"
    papers_dir.mkdir(parents=True)

    # Create an existing paper with the base ID
    post = frontmatter.Post("# Existing")
    post.metadata = {"id": "paper-green-and-ampt-model-1911", "type": "paper"}
    (papers_dir / "green-and-ampt-model-1911.md").write_text(frontmatter.dumps(post))

    # generate_id with kb_path should detect collision and return -2
    pid = generate_id("paper", "Green and Ampt Model", year=1911, kb_path=tmp_path)
    assert pid == "paper-green-and-ampt-model-1911-2"


def test_generate_id_no_collision_without_kb_path() -> None:
    """Without kb_path, no collision check — returns base ID."""
    pid = generate_id("paper", "Green and Ampt Model", year=1911)
    assert pid == "paper-green-and-ampt-model-1911"


def test_build_paper_frontmatter() -> None:
    fm = build_frontmatter(
        type="paper",
        title="Green and Ampt Model",
        authors=["Green, W.H.", "Ampt, G.A."],
        year=1911,
        topic="hydrology",
    )
    assert fm["type"] == "paper"
    assert fm["title"] == "Green and Ampt Model"
    assert fm["authors"] == ["Green, W.H.", "Ampt, G.A."]
    assert fm["year"] == 1911
    assert fm["topic"] == "hydrology"
    assert "added" in fm
