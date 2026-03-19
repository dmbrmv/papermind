"""Tests for markdown paper ingestion."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import frontmatter as fm_lib

from papermind.catalog.index import CatalogEntry, CatalogIndex
from papermind.config import PaperMindConfig
from papermind.ingestion.paper import ingest_paper, ingest_papers_batch
from papermind.ingestion.validation import ValidationError, validate_markdown

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path) -> PaperMindConfig:
    return PaperMindConfig(base_path=tmp_path)


def _make_kb(tmp_path: Path) -> Path:
    """Initialise a minimal KB with catalog.json."""
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")
    return kb


def _write_md(path: Path, content: str) -> Path:
    """Write markdown content to a file."""
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# validate_markdown
# ---------------------------------------------------------------------------


class TestValidateMarkdown:
    """Validate markdown file checks."""

    def test_valid_markdown(self, tmp_path: Path) -> None:
        md = tmp_path / "paper.md"
        md.write_text("# My Paper\n\nSome content about hydrology.\n")
        validate_markdown(md)  # should not raise

    def test_valid_markdown_extension(self, tmp_path: Path) -> None:
        md = tmp_path / "paper.markdown"
        md.write_text("# Another Paper\n\nContent.\n")
        validate_markdown(md)

    def test_wrong_extension(self, tmp_path: Path) -> None:
        txt = tmp_path / "paper.txt"
        txt.write_text("# Not a markdown file\n")
        with __import__("pytest").raises(ValidationError, match="Not a markdown"):
            validate_markdown(txt)

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        with __import__("pytest").raises(ValidationError, match="not found"):
            validate_markdown(tmp_path / "missing.md")

    def test_too_small(self, tmp_path: Path) -> None:
        md = tmp_path / "tiny.md"
        md.write_text("# Hi")  # 4 bytes — below MIN_MD_SIZE (10)
        with __import__("pytest").raises(ValidationError, match="too small"):
            validate_markdown(md)

    def test_control_chars_in_filename(self, tmp_path: Path) -> None:
        with __import__("pytest").raises(ValidationError, match="control character"):
            validate_markdown(tmp_path / "bad\nfile.md")


# ---------------------------------------------------------------------------
# ingest_paper — markdown files (no OCR)
# ---------------------------------------------------------------------------


class TestIngestMarkdownPaper:
    """Verify markdown ingestion skips OCR and uses existing content."""

    def test_basic_markdown_ingestion(self, tmp_path: Path) -> None:
        """A plain .md file is ingested without OCR."""
        kb = _make_kb(tmp_path)
        md = _write_md(
            tmp_path / "paper.md",
            "# Rainfall-Runoff Modeling (2020)\n\nDOI: 10.1234/rrm2020.\n\nContent.\n",
        )
        cfg = _make_config(tmp_path)

        entry = ingest_paper(md, "hydrology", kb, cfg, no_reindex=True)

        assert entry is not None
        assert entry.type == "paper"
        assert entry.title == "Rainfall-Runoff Modeling (2020)"
        assert entry.doi == "10.1234/rrm2020"
        assert entry.topic == "hydrology"

    def test_markdown_frontmatter_metadata(self, tmp_path: Path) -> None:
        """Existing YAML frontmatter is respected."""
        kb = _make_kb(tmp_path)
        content = (
            "---\n"
            "title: My Custom Title\n"
            "doi: 10.5555/custom\n"
            "year: 2019\n"
            "abstract: A paper about water.\n"
            "---\n\n"
            "# Different Heading\n\n"
            "Body text.\n"
        )
        md = _write_md(tmp_path / "paper.md", content)
        cfg = _make_config(tmp_path)

        entry = ingest_paper(md, "hydrology", kb, cfg, no_reindex=True)

        assert entry is not None
        assert entry.title == "My Custom Title"
        assert entry.doi == "10.5555/custom"

        # Check the written paper.md has the frontmatter fields
        written = list((kb / "papers" / "hydrology").rglob("paper.md"))[0]
        post = fm_lib.load(written)
        assert post.metadata["year"] == 2019
        assert post.metadata["abstract"] == "A paper about water."

    def test_markdown_no_frontmatter(self, tmp_path: Path) -> None:
        """Markdown without frontmatter extracts metadata from content."""
        kb = _make_kb(tmp_path)
        md = _write_md(
            tmp_path / "notes.md",
            "# SWAT Model Calibration (2021)\n\nDOI: 10.9999/swat.\n\nPaper content.\n",
        )
        cfg = _make_config(tmp_path)

        entry = ingest_paper(md, "hydrology", kb, cfg, no_reindex=True)

        assert entry is not None
        assert entry.title == "SWAT Model Calibration (2021)"
        assert entry.doi == "10.9999/swat"

    def test_markdown_original_copied(self, tmp_path: Path) -> None:
        """Original .md is copied as original.md (not original.pdf)."""
        kb = _make_kb(tmp_path)
        md = _write_md(
            tmp_path / "paper.md",
            "# Test Paper\n\nSome body text goes here.\n",
        )
        cfg = _make_config(tmp_path)

        entry = ingest_paper(md, "general", kb, cfg, no_reindex=True)

        assert entry is not None
        paper_dir = (kb / "papers" / "general").iterdir().__next__()
        assert (paper_dir / "original.md").exists()
        assert not (paper_dir / "original.pdf").exists()

    def test_markdown_catalog_updated(self, tmp_path: Path) -> None:
        """catalog.json is updated after markdown ingestion."""
        kb = _make_kb(tmp_path)
        md = _write_md(
            tmp_path / "paper.md",
            "# Catalog Test Paper (2022)\n\nSome content.\n",
        )
        cfg = _make_config(tmp_path)

        ingest_paper(md, "general", kb, cfg, no_reindex=True)

        catalog = json.loads((kb / "catalog.json").read_text())
        assert len(catalog) == 1
        assert catalog[0]["type"] == "paper"

    def test_markdown_duplicate_doi_skipped(self, tmp_path: Path) -> None:
        """Markdown with existing DOI is skipped."""
        kb = _make_kb(tmp_path)
        cfg = _make_config(tmp_path)

        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-existing-2020",
                type="paper",
                path="papers/hydrology/existing.md",
                doi="10.1234/existing",
            )
        )

        md = _write_md(
            tmp_path / "paper.md",
            "---\ndoi: 10.1234/existing\n---\n\n# Duplicate\n\n",
        )
        result = ingest_paper(md, "hydrology", kb, cfg, no_reindex=True)
        assert result is None

    def test_markdown_no_ocr_called(self, tmp_path: Path) -> None:
        """OCR should never be called for .md files."""
        kb = _make_kb(tmp_path)
        md = _write_md(
            tmp_path / "paper.md",
            "# No OCR Needed\n\nThis is plain markdown.\n",
        )
        cfg = _make_config(tmp_path)

        with patch(
            "papermind.ingestion.paper.convert_pdf",
            side_effect=AssertionError("OCR should not be called for markdown"),
        ):
            entry = ingest_paper(md, "general", kb, cfg, no_reindex=True)

        assert entry is not None


# ---------------------------------------------------------------------------
# Batch ingestion — mixed PDF + markdown
# ---------------------------------------------------------------------------


class TestBatchMarkdownIngestion:
    """Verify batch mode handles markdown files."""

    def test_batch_finds_markdown_files(self, tmp_path: Path) -> None:
        """Batch mode picks up .md files alongside PDFs."""
        kb = _make_kb(tmp_path)
        cfg = _make_config(tmp_path)
        batch_dir = tmp_path / "papers"
        batch_dir.mkdir()

        _write_md(
            batch_dir / "paper1.md",
            "# First Paper (2020)\n\nContent of first paper.\n",
        )
        _write_md(
            batch_dir / "paper2.md",
            "# Second Paper (2021)\n\nContent of second paper.\n",
        )

        result = ingest_papers_batch(batch_dir, "hydrology", kb, cfg)
        assert result.ingested == 2
        assert result.failed == 0

    def test_batch_markdown_subdirectory(self, tmp_path: Path) -> None:
        """Batch mode finds .md files in subdirectories."""
        kb = _make_kb(tmp_path)
        cfg = _make_config(tmp_path)
        batch_dir = tmp_path / "papers"
        sub = batch_dir / "subdir"
        sub.mkdir(parents=True)

        _write_md(sub / "nested.md", "# Nested Paper\n\nDeep in a subfolder.\n")

        result = ingest_papers_batch(batch_dir, "general", kb, cfg)
        assert result.ingested == 1
