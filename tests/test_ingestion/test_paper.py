"""Tests for paper ingestion — Marker subprocess wrapper."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hydrofound.catalog.index import CatalogIndex
from hydrofound.config import HydroFoundConfig
from hydrofound.ingestion.paper import convert_pdf, extract_metadata, ingest_paper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PDF_MAGIC = b"%PDF-1.4\n" + b"x" * 2048  # passes validate_pdf


def _make_pdf(path: Path) -> Path:
    """Write a minimal valid PDF stub."""
    path.write_bytes(PDF_MAGIC)
    return path


def _make_config(tmp_path: Path, *, marker_path: str = "marker") -> HydroFoundConfig:
    return HydroFoundConfig(base_path=tmp_path, marker_path=marker_path)


def _make_kb(tmp_path: Path) -> Path:
    """Initialise a minimal KB with catalog.json."""
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".hydrofound").mkdir()
    (kb / "catalog.json").write_text("[]")
    return kb


def _marker_subprocess_result(stdout: str = "", returncode: int = 0) -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = ""
    return result


# ---------------------------------------------------------------------------
# convert_pdf — command construction
# ---------------------------------------------------------------------------


class TestConvertPdfCommandConstruction:
    """Verify the exact subprocess command passed to Marker."""

    def test_command_is_list_not_shell(self, tmp_path: Path) -> None:
        """subprocess.run must receive a list, never shell=True."""
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        # Simulate Marker writing its output directory.
        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# Title\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _marker_subprocess_result()
            convert_pdf(pdf, cfg)

            call_args, call_kwargs = mock_run.call_args
            cmd = call_args[0]
            assert isinstance(cmd, list), "cmd must be a list (never shell=True)"
            assert "shell" not in call_kwargs or call_kwargs.get("shell") is not True

    def test_command_structure(self, tmp_path: Path) -> None:
        """Command must be ['marker', str(path), '--output_format', 'markdown']."""
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# Title\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _marker_subprocess_result()
            convert_pdf(pdf, cfg)

            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "marker"
            assert cmd[1] == str(pdf)
            assert "--output_format" in cmd
            idx = cmd.index("--output_format")
            assert cmd[idx + 1] == "markdown"

    def test_custom_marker_path(self, tmp_path: Path) -> None:
        """marker_path from config is used as the first argument."""
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path, marker_path="/opt/marker/bin/marker")

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# Title\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _marker_subprocess_result()
            convert_pdf(pdf, cfg)

            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "/opt/marker/bin/marker"

    def test_use_llm_flag_added_when_enabled(self, tmp_path: Path) -> None:
        """--use_llm flag is appended when marker_use_llm=True."""
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)
        cfg.marker_use_llm = True

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# Title\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _marker_subprocess_result()
            convert_pdf(pdf, cfg)

            cmd = mock_run.call_args[0][0]
            assert "--use_llm" in cmd

    def test_use_llm_flag_absent_when_disabled(self, tmp_path: Path) -> None:
        """--use_llm is NOT added when marker_use_llm=False (default)."""
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)
        cfg.marker_use_llm = False

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# Title\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _marker_subprocess_result()
            convert_pdf(pdf, cfg)

            cmd = mock_run.call_args[0][0]
            assert "--use_llm" not in cmd


# ---------------------------------------------------------------------------
# convert_pdf — output resolution
# ---------------------------------------------------------------------------


class TestConvertPdfOutputResolution:
    """Verify the output file discovery logic."""

    def test_reads_md_from_output_directory(self, tmp_path: Path) -> None:
        """Marker's primary output: <stem>/<stem>.md directory layout."""
        pdf = _make_pdf(tmp_path / "greenampt.pdf")
        cfg = _make_config(tmp_path)

        out_dir = tmp_path / "greenampt"
        out_dir.mkdir()
        expected = "# Green and Ampt Model\n\nContent here."
        (out_dir / "greenampt.md").write_text(expected)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _marker_subprocess_result()
            md = convert_pdf(pdf, cfg)

        assert md == expected

    def test_falls_back_to_sibling_md_file(self, tmp_path: Path) -> None:
        """Falls back to <input>.md beside the PDF when no output dir exists."""
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        sibling = tmp_path / "paper.md"
        sibling.write_text("# Sibling Output\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _marker_subprocess_result()
            md = convert_pdf(pdf, cfg)

        assert "Sibling Output" in md

    def test_falls_back_to_stdout(self, tmp_path: Path) -> None:
        """Falls back to stdout when no files are written."""
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _marker_subprocess_result(
                stdout="# Stdout Title\nBody text.\n"
            )
            md = convert_pdf(pdf, cfg)

        assert "Stdout Title" in md

    def test_raises_runtime_error_when_no_output(self, tmp_path: Path) -> None:
        """RuntimeError when Marker produces neither files nor stdout."""
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _marker_subprocess_result(stdout="")
            with pytest.raises(RuntimeError, match="no output"):
                convert_pdf(pdf, cfg)


# ---------------------------------------------------------------------------
# convert_pdf — error handling
# ---------------------------------------------------------------------------


class TestConvertPdfErrors:
    """Error paths: Marker not installed, non-zero exit."""

    def test_raises_file_not_found_when_marker_missing(self, tmp_path: Path) -> None:
        """FileNotFoundError when the Marker binary does not exist."""
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        with patch(
            "subprocess.run", side_effect=FileNotFoundError("marker: not found")
        ):
            with pytest.raises(FileNotFoundError, match="Marker not found"):
                convert_pdf(pdf, cfg)

    def test_raises_runtime_error_on_nonzero_return(self, tmp_path: Path) -> None:
        """RuntimeError when Marker exits with non-zero return code."""
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        bad_result = MagicMock()
        bad_result.returncode = 1
        bad_result.stdout = ""
        bad_result.stderr = "Error: unsupported PDF format"

        with patch("subprocess.run", return_value=bad_result):
            with pytest.raises(RuntimeError, match="Marker failed"):
                convert_pdf(pdf, cfg)

    def test_error_message_contains_stderr(self, tmp_path: Path) -> None:
        """RuntimeError message includes Marker's stderr output."""
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        bad_result = MagicMock()
        bad_result.returncode = 2
        bad_result.stdout = ""
        bad_result.stderr = "segmentation fault in layout model"

        with patch("subprocess.run", return_value=bad_result):
            with pytest.raises(RuntimeError, match="segmentation fault"):
                convert_pdf(pdf, cfg)


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
        # First # heading (regardless of position) should be picked up
        assert meta["title"] == "Real Title"

    def test_no_title_when_no_h1(self) -> None:
        md = "## Subtitle Only\n\nNo level-1 heading."
        meta = extract_metadata(md)
        assert "title" not in meta

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

        md_content = "# My Paper (2020)\n\nDOI: 10.9999/test.2020.\n"
        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text(md_content)

        with patch("subprocess.run", return_value=_marker_subprocess_result()):
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

        md_content = "# Green Ampt Paper (1911)\n\nDOI: 10.1234/ga1911.\n"
        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text(md_content)

        with patch("subprocess.run", return_value=_marker_subprocess_result()):
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

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# Title\n")

        with patch("subprocess.run", return_value=_marker_subprocess_result()):
            ingest_paper(pdf, "general", kb, cfg, no_reindex=True)

        written = list((kb / "papers" / "general").glob("*.md"))[0]
        post = fm_lib.load(written)
        assert "added" in post.metadata

    def test_frontmatter_no_doi_field_when_absent(self, tmp_path: Path) -> None:
        """doi key should be omitted (or empty) when not found in markdown."""
        import frontmatter as fm_lib

        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# A Paper Without DOI\n")

        with patch("subprocess.run", return_value=_marker_subprocess_result()):
            ingest_paper(pdf, "general", kb, cfg, no_reindex=True)

        written = list((kb / "papers" / "general").glob("*.md"))[0]
        post = fm_lib.load(written)
        # doi should be absent or empty string — not a garbage value
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

        # Pre-populate catalog with a known DOI.
        from hydrofound.catalog.index import CatalogEntry

        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-existing-2020",
                type="paper",
                path="papers/hydrology/existing-2020.md",
                doi="10.9999/duplicate",
            )
        )

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text(
            "# Duplicate (2020)\n\nDOI: 10.9999/duplicate.\n"
        )

        with patch("subprocess.run", return_value=_marker_subprocess_result()):
            result = ingest_paper(pdf, "hydrology", kb, cfg, no_reindex=True)

        assert result is None

    def test_duplicate_doi_does_not_write_file(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        from hydrofound.catalog.index import CatalogEntry

        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-existing-2020",
                type="paper",
                path="papers/hydrology/existing-2020.md",
                doi="10.9999/duplicate",
            )
        )

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text(
            "# Duplicate (2020)\n\nDOI: 10.9999/duplicate.\n"
        )

        with patch("subprocess.run", return_value=_marker_subprocess_result()):
            ingest_paper(pdf, "hydrology", kb, cfg, no_reindex=True)

        # No new file should have been written for this topic
        topic_dir = kb / "papers" / "hydrology"
        written_files = list(topic_dir.glob("*.md")) if topic_dir.exists() else []
        assert len(written_files) == 0

    def test_unique_doi_is_ingested(self, tmp_path: Path) -> None:
        """A paper with a different DOI is ingested normally."""
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        from hydrofound.catalog.index import CatalogEntry

        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-other-2018",
                type="paper",
                path="papers/hydrology/other-2018.md",
                doi="10.9999/other",
            )
        )

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text(
            "# New Paper (2021)\n\nDOI: 10.9999/new-unique.\n"
        )

        with patch("subprocess.run", return_value=_marker_subprocess_result()):
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

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# New Paper (2022)\n\nDOI: 10.1/new.\n")

        with patch("subprocess.run", return_value=_marker_subprocess_result()):
            ingest_paper(pdf, "general", kb, cfg, no_reindex=True)

        catalog = json.loads((kb / "catalog.json").read_text())
        assert len(catalog) == 1
        assert catalog[0]["type"] == "paper"

    def test_catalog_md_updated(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        (kb / "catalog.md").write_text("")  # start empty
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# Hydrology Paper (2019)\n\n")

        with patch("subprocess.run", return_value=_marker_subprocess_result()):
            ingest_paper(pdf, "hydrology", kb, cfg, no_reindex=True)

        catalog_md = (kb / "catalog.md").read_text()
        assert "Hydrology Paper" in catalog_md

    def test_returned_entry_fields(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text(
            "# SWAT+ Model (2021)\n\nDOI: 10.5555/swat2021.\n"
        )

        with patch("subprocess.run", return_value=_marker_subprocess_result()):
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

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# Test\n")

        assert not (kb / "papers" / "newtopic").exists()

        with patch("subprocess.run", return_value=_marker_subprocess_result()):
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

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# Title\n")

        with patch(
            "subprocess.run", return_value=_marker_subprocess_result()
        ) as mock_run:
            ingest_paper(pdf, "general", kb, cfg, no_reindex=True)

        # Only one subprocess.run call: Marker. No qmd call.
        assert mock_run.call_count == 1
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "marker"

    def test_reindex_attempted_when_flag_false(self, tmp_path: Path) -> None:
        """With no_reindex=False and qmd on PATH, a second subprocess.run is issued."""
        kb = _make_kb(tmp_path)
        pdf = _make_pdf(tmp_path / "paper.pdf")
        cfg = _make_config(tmp_path)

        out_dir = tmp_path / "paper"
        out_dir.mkdir()
        (out_dir / "paper.md").write_text("# Title\n")

        with (
            patch(
                "subprocess.run", return_value=_marker_subprocess_result()
            ) as mock_run,
            patch("shutil.which", return_value="/usr/bin/qmd"),
        ):
            ingest_paper(pdf, "general", kb, cfg, no_reindex=False)

        # Two calls: marker + qmd reindex
        assert mock_run.call_count == 2
        qmd_cmd = mock_run.call_args_list[1][0][0]
        assert "qmd" in qmd_cmd[0]
        assert "reindex" in qmd_cmd
