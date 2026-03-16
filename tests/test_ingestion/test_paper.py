"""Tests for paper ingestion — GLM-OCR conversion + metadata + catalog."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from papermind.catalog.index import CatalogIndex
from papermind.config import PaperMindConfig
from papermind.ingestion.paper import convert_pdf, extract_metadata, ingest_paper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PDF_MAGIC = b"%PDF-1.4\n" + b"x" * 2048  # passes validate_pdf


def _make_pdf(path: Path) -> Path:
    """Write a minimal valid PDF stub."""
    path.write_bytes(PDF_MAGIC)
    return path


def _make_config(tmp_path: Path) -> PaperMindConfig:
    return PaperMindConfig(base_path=tmp_path)


def _make_kb(tmp_path: Path) -> Path:
    """Initialise a minimal KB with catalog.json."""
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")
    return kb


def _mock_convert(md_content: str = "# Title\n"):
    """Return a patch context manager that mocks convert_pdf_glm."""
    return patch(
        "papermind.ingestion.glm_ocr.convert_pdf_glm",
        return_value=md_content,
    )


# ---------------------------------------------------------------------------
# convert_pdf — routes to GLM-OCR
# ---------------------------------------------------------------------------


class TestConvertPdfDispatch:
    """Verify convert_pdf delegates to GLM-OCR."""

    def test_calls_glm_ocr(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with _mock_convert("# Output\n") as mock_glm:
            result = convert_pdf(pdf, cfg)

        mock_glm.assert_called_once()
        assert result == "# Output\n"

    def test_passes_model_and_dpi_from_config(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)
        cfg.ocr_model = "custom/model"
        cfg.ocr_dpi = 200

        with _mock_convert("# X\n") as mock_glm:
            convert_pdf(pdf, cfg)

        _, kwargs = mock_glm.call_args
        assert kwargs["model_name"] == "custom/model"
        assert kwargs["dpi"] == 200


# ---------------------------------------------------------------------------
# extract_metadata
# ---------------------------------------------------------------------------


class TestExtractMetadata:
    """Verify metadata extraction from raw markdown."""

    def test_extracts_title_from_first_h1(self) -> None:
        md = "# Green and Ampt Infiltration Model\n\nSome content."
        meta = extract_metadata(md)
        assert meta["title"] == "Green and Ampt Infiltration Model"

    def test_ignores_h2_for_title(self) -> None:
        md = "## Not a title\n\n# Real Title\n"
        meta = extract_metadata(md)
        assert meta["title"] == "Real Title"

    def test_fallback_title_when_no_h1(self) -> None:
        """When no # heading exists, first uppercase line is used as title."""
        md = "## Subtitle Only\n\nNo level-1 heading."
        meta = extract_metadata(md)
        # Fallback picks first line starting with uppercase, >10 chars
        assert meta["title"] == "No level-1 heading."

    def test_extracts_doi(self) -> None:
        md = "# Paper\n\nhttps://doi.org/10.1002/hyp.14561 is the DOI.\n"
        meta = extract_metadata(md)
        assert meta["doi"] == "10.1002/hyp.14561"

    def test_doi_trailing_punctuation_stripped(self) -> None:
        md = "doi: 10.5194/hess-25-2019-2021.\n"
        meta = extract_metadata(md)
        assert meta["doi"] == "10.5194/hess-25-2019-2021"

    def test_no_doi_when_absent(self) -> None:
        md = "# A paper with no DOI\n\nNo references.\n"
        meta = extract_metadata(md)
        assert "doi" not in meta

    def test_extracts_year_in_parentheses(self) -> None:
        md = "# Title\n\nPublished (2021) in WRR.\n"
        meta = extract_metadata(md)
        assert meta["year"] == 2021

    def test_year_out_of_range_ignored(self) -> None:
        md = "# Title\n\nSome value (1800) in the intro.\n"
        meta = extract_metadata(md)
        assert "year" not in meta

    def test_year_only_within_first_2000_chars(self) -> None:
        prefix = "# Title\n" + "x" * 2100
        md = prefix + " (2021) late mention."
        meta = extract_metadata(md)
        assert "year" not in meta

    def test_all_fields_together(self) -> None:
        md = (
            "# Soil Water Assessment Tool (2012)\n\n"
            "DOI: 10.1016/j.jhydrol.2021.126601.\n\n"
            "Details follow.\n"
        )
        meta = extract_metadata(md)
        assert meta["title"] == "Soil Water Assessment Tool (2012)"
        assert meta["doi"] == "10.1016/j.jhydrol.2021.126601"
        assert meta["year"] == 2012

    def test_empty_markdown_returns_empty_dict(self) -> None:
        assert extract_metadata("") == {}


# ---------------------------------------------------------------------------
# ingest_paper — frontmatter generation
# ---------------------------------------------------------------------------


class TestIngestPaperFrontmatter:
    """Verify frontmatter is correctly built and written."""

    def test_frontmatter_type_is_paper(self, tmp_path: Path) -> None:
        import frontmatter as fm_lib

        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with _mock_convert("# My Paper (2020)\n\nDOI: 10.9999/test.2020.\n"):
            entry = ingest_paper(pdf, "hydrology", kb, cfg, no_reindex=True)

        assert entry is not None
        written = list((kb / "papers" / "hydrology").glob("*.md"))[0]
        post = fm_lib.load(written)
        assert post.metadata["type"] == "paper"

    def test_frontmatter_contains_doi_title_year(self, tmp_path: Path) -> None:
        import frontmatter as fm_lib

        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with _mock_convert("# Green Ampt Paper (1911)\n\nDOI: 10.1234/ga1911.\n"):
            ingest_paper(pdf, "infiltration", kb, cfg, no_reindex=True)

        written = list((kb / "papers" / "infiltration").glob("*.md"))[0]
        post = fm_lib.load(written)
        assert post.metadata["title"] == "Green Ampt Paper (1911)"
        assert post.metadata["doi"] == "10.1234/ga1911"
        assert post.metadata["year"] == 1911

    def test_frontmatter_has_added_date(self, tmp_path: Path) -> None:
        import frontmatter as fm_lib

        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with _mock_convert("# Title\n"):
            ingest_paper(pdf, "general", kb, cfg, no_reindex=True)

        written = list((kb / "papers" / "general").glob("*.md"))[0]
        post = fm_lib.load(written)
        assert "added" in post.metadata

    def test_frontmatter_no_doi_field_when_absent(self, tmp_path: Path) -> None:
        import frontmatter as fm_lib

        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with _mock_convert("# A Paper Without DOI\n"):
            ingest_paper(pdf, "general", kb, cfg, no_reindex=True)

        written = list((kb / "papers" / "general").glob("*.md"))[0]
        post = fm_lib.load(written)
        doi_val = post.metadata.get("doi", "")
        assert doi_val == ""


# ---------------------------------------------------------------------------
# ingest_paper — re-ingestion (duplicate DOI)
# ---------------------------------------------------------------------------


class TestIngestPaperDuplicateDoi:
    """Immutable policy: same DOI must be silently skipped."""

    def test_duplicate_doi_returns_none(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        from papermind.catalog.index import CatalogEntry

        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-existing-2020",
                type="paper",
                path="papers/hydrology/existing-2020.md",
                doi="10.9999/duplicate",
            )
        )

        with _mock_convert("# Duplicate (2020)\n\nDOI: 10.9999/duplicate.\n"):
            result = ingest_paper(pdf, "hydrology", kb, cfg, no_reindex=True)

        assert result is None

    def test_duplicate_doi_does_not_write_file(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        from papermind.catalog.index import CatalogEntry

        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-existing-2020",
                type="paper",
                path="papers/hydrology/existing-2020.md",
                doi="10.9999/duplicate",
            )
        )

        with _mock_convert("# Duplicate (2020)\n\nDOI: 10.9999/duplicate.\n"):
            ingest_paper(pdf, "hydrology", kb, cfg, no_reindex=True)

        topic_dir = kb / "papers" / "hydrology"
        written_files = list(topic_dir.glob("*.md")) if topic_dir.exists() else []
        assert len(written_files) == 0

    def test_unique_doi_is_ingested(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        from papermind.catalog.index import CatalogEntry

        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-other-2018",
                type="paper",
                path="papers/hydrology/other-2018.md",
                doi="10.9999/other",
            )
        )

        with _mock_convert("# New Paper (2021)\n\nDOI: 10.9999/new-unique.\n"):
            entry = ingest_paper(pdf, "hydrology", kb, cfg, no_reindex=True)

        assert entry is not None
        assert entry.doi == "10.9999/new-unique"


# ---------------------------------------------------------------------------
# ingest_paper — catalog updates
# ---------------------------------------------------------------------------


class TestIngestPaperCatalogUpdates:
    """Verify catalog.json and catalog.md are updated correctly."""

    def test_catalog_json_updated(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with _mock_convert("# New Paper (2022)\n\nDOI: 10.1/new.\n"):
            ingest_paper(pdf, "general", kb, cfg, no_reindex=True)

        catalog = json.loads((kb / "catalog.json").read_text())
        assert len(catalog) == 1
        assert catalog[0]["type"] == "paper"

    def test_catalog_md_updated(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        (kb / "catalog.md").write_text("")
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with _mock_convert("# Hydrology Paper (2019)\n\n"):
            ingest_paper(pdf, "hydrology", kb, cfg, no_reindex=True)

        catalog_md = (kb / "catalog.md").read_text()
        assert "Hydrology Paper" in catalog_md

    def test_returned_entry_fields(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with _mock_convert("# SWAT+ Model (2021)\n\nDOI: 10.5555/swat2021.\n"):
            entry = ingest_paper(pdf, "swat", kb, cfg, no_reindex=True)

        assert entry is not None
        assert entry.type == "paper"
        assert entry.topic == "swat"
        assert entry.doi == "10.5555/swat2021"
        assert "papers/swat/" in entry.path

    def test_papers_directory_created(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        assert not (kb / "papers" / "newtopic").exists()

        with _mock_convert("# Test\n"):
            ingest_paper(pdf, "newtopic", kb, cfg, no_reindex=True)

        assert (kb / "papers" / "newtopic").is_dir()


# ---------------------------------------------------------------------------
# ingest_paper — --no-reindex flag
# ---------------------------------------------------------------------------


class TestNoReindexFlag:
    """--no-reindex suppresses qmd invocation."""

    def test_no_reindex_does_not_call_qmd(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with (
            _mock_convert("# Title\n"),
            patch("subprocess.run") as mock_run,
        ):
            ingest_paper(pdf, "general", kb, cfg, no_reindex=True)

        # No subprocess.run calls at all (qmd not called)
        mock_run.assert_not_called()

    def test_reindex_attempted_when_flag_false(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with (
            _mock_convert("# Title\n"),
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/qmd"),
        ):
            ingest_paper(pdf, "general", kb, cfg, no_reindex=False)

        # One call: qmd collection refresh
        assert mock_run.call_count == 1
        qmd_cmd = mock_run.call_args[0][0]
        assert qmd_cmd[0] == "qmd"
        assert "collection" in qmd_cmd


# ---------------------------------------------------------------------------
# E3: Title similarity deduplication (Batch D)
# ---------------------------------------------------------------------------


class TestTitleSimilarityDedup:
    """Papers whose titles are >90% similar to an existing paper are rejected."""

    def test_title_similarity_dedup(self, tmp_path: Path) -> None:
        """Ingesting a paper with a >90% title match returns None (near-dup rejected)."""
        from papermind.catalog.index import CatalogEntry

        kb = _make_kb(tmp_path)
        cfg = _make_config(tmp_path)

        # Seed the catalog with an existing paper.
        # "SWAT Calibration Methods" vs "SWAT Calibration Method" has ~97.9%
        # similarity — well above the 90% threshold in ingest_paper.
        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-swat-calib-2020",
                type="paper",
                path="papers/hydrology/swat-calib-2020.md",
                title="SWAT Calibration Methods",
            )
        )

        # Near-duplicate: only the final 's' differs (ratio ≈ 0.979)
        pdf = _make_pdf(tmp_path / "near-dup.pdf")
        with _mock_convert("# SWAT Calibration Method\n\n"):
            result = ingest_paper(pdf, "hydrology", kb, cfg, no_reindex=True)

        assert result is None, (
            "Expected None (title similarity dedup), but ingest_paper returned an entry"
        )

    def test_title_similarity_distinct_title_ingested(self, tmp_path: Path) -> None:
        """A paper with a sufficiently different title is ingested normally."""
        from papermind.catalog.index import CatalogEntry

        kb = _make_kb(tmp_path)
        cfg = _make_config(tmp_path)

        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-swat-calib-2020",
                type="paper",
                path="papers/hydrology/swat-calib-2020.md",
                title="SWAT Calibration Methods",
            )
        )

        pdf = _make_pdf(tmp_path / "different-paper.pdf")
        with _mock_convert(
            "# Deep Learning for Streamflow Prediction (2022)\n\nDOI: 10.9999/dl2022.\n"
        ):
            result = ingest_paper(pdf, "hydrology", kb, cfg, no_reindex=True)

        assert result is not None, "Expected a CatalogEntry for a distinct title"
