"""Tests for batch paper ingestion — folder walk, dedup, single reindex."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hydrofound.catalog.index import CatalogEntry, CatalogIndex
from hydrofound.config import HydroFoundConfig
from hydrofound.ingestion.paper import BatchResult, ingest_papers_batch

# ---------------------------------------------------------------------------
# Shared helpers (mirror test_paper.py conventions)
# ---------------------------------------------------------------------------

PDF_MAGIC = b"%PDF-1.4\n" + b"x" * 2048  # passes validate_pdf


def _make_pdf(path: Path) -> Path:
    """Write a minimal valid PDF stub."""
    path.write_bytes(PDF_MAGIC)
    return path


def _make_config(tmp_path: Path, *, marker_path: str = "marker") -> HydroFoundConfig:
    return HydroFoundConfig(
        base_path=tmp_path, converter="marker", marker_path=marker_path
    )


def _make_kb(tmp_path: Path) -> Path:
    """Initialise a minimal KB with catalog.json."""
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".hydrofound").mkdir()
    (kb / "catalog.json").write_text("[]")
    return kb


def _marker_ok(stdout: str = "") -> MagicMock:
    """Return a successful subprocess.run mock result."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = stdout
    result.stderr = ""
    return result


def _marker_fail() -> MagicMock:
    """Return a failed subprocess.run mock result (non-zero exit)."""
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    result.stderr = "Marker error"
    return result


def _setup_marker_output(pdf_path: Path, md_content: str) -> None:
    """Create the Marker output directory that convert_pdf reads from."""
    out_dir = pdf_path.parent / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{pdf_path.stem}.md").write_text(md_content)


# ---------------------------------------------------------------------------
# BatchResult
# ---------------------------------------------------------------------------


class TestBatchResult:
    """Unit tests for the BatchResult dataclass."""

    def test_initial_counts_are_zero(self) -> None:
        r = BatchResult()
        assert r.ingested == 0
        assert r.skipped == 0
        assert r.failed == 0
        assert r.errors == {}

    def test_str_format(self) -> None:
        r = BatchResult()
        r.ingested = 3
        r.skipped = 1
        r.failed = 1
        assert str(r) == "3 ingested, 1 skipped, 1 failed"


# ---------------------------------------------------------------------------
# ingest_papers_batch — happy path
# ---------------------------------------------------------------------------


class TestBatchAllSucceed:
    """All PDFs in the folder are ingested successfully."""

    def test_all_three_ingested(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        papers = [
            ("paper_a", "# Paper A (2020)\nDOI: 10.1111/a.2020.\n"),
            ("paper_b", "# Paper B (2021)\nDOI: 10.1111/b.2021.\n"),
            ("paper_c", "# Paper C (2022)\nDOI: 10.1111/c.2022.\n"),
        ]

        for stem, md in papers:
            pdf = _make_pdf(folder / f"{stem}.pdf")
            _setup_marker_output(pdf, md)

        with patch("subprocess.run", return_value=_marker_ok()):
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.ingested == 3
        assert result.skipped == 0
        assert result.failed == 0

    def test_catalog_has_three_entries(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        for i in range(3):
            pdf = _make_pdf(folder / f"paper_{i}.pdf")
            _setup_marker_output(
                pdf, f"# Paper {i} ({2020 + i})\nDOI: 10.1234/paper{i}year.\n"
            )

        with patch("subprocess.run", return_value=_marker_ok()):
            ingest_papers_batch(folder, "hydrology", kb, cfg)

        catalog = json.loads((kb / "catalog.json").read_text())
        assert len(catalog) == 3

    def test_markdown_files_written_to_topic_dir(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        for i in range(2):
            pdf = _make_pdf(folder / f"doc_{i}.pdf")
            _setup_marker_output(pdf, f"# Doc {i} ({2019 + i})\nDOI: 10.2/{i}.\n")

        with patch("subprocess.run", return_value=_marker_ok()):
            ingest_papers_batch(folder, "swat", kb, cfg)

        topic_dir = kb / "papers" / "swat"
        assert topic_dir.is_dir()
        assert len(list(topic_dir.glob("*.md"))) == 2


# ---------------------------------------------------------------------------
# ingest_papers_batch — duplicate DOI skip
# ---------------------------------------------------------------------------


class TestBatchDuplicateSkip:
    """Papers with a DOI already in the catalog are counted as skipped."""

    def test_duplicate_counted_as_skipped(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        # Pre-populate catalog with a DOI that will be a duplicate.
        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-existing",
                type="paper",
                path="papers/hydrology/existing.md",
                doi="10.9999/dup",
            )
        )

        # duplicate — same DOI (must use valid DOI format: 10.XXXX/... with 4+ digits)
        dup_pdf = _make_pdf(folder / "dup.pdf")
        _setup_marker_output(dup_pdf, "# Dup Paper (2021)\nDOI: 10.9999/dup.\n")

        # new — different DOI
        new_pdf = _make_pdf(folder / "new.pdf")
        _setup_marker_output(new_pdf, "# New Paper (2022)\nDOI: 10.9999/new.\n")

        with patch("subprocess.run", return_value=_marker_ok()):
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.skipped == 1
        assert result.ingested == 1
        assert result.failed == 0

    def test_duplicate_not_written_to_disk(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-existing",
                type="paper",
                path="papers/hydrology/existing.md",
                doi="10.9999/dup",
            )
        )

        dup_pdf = _make_pdf(folder / "dup.pdf")
        _setup_marker_output(dup_pdf, "# Dup Paper\nDOI: 10.9999/dup.\n")

        with patch("subprocess.run", return_value=_marker_ok()):
            ingest_papers_batch(folder, "hydrology", kb, cfg)

        topic_dir = kb / "papers" / "hydrology"
        written = list(topic_dir.glob("*.md")) if topic_dir.exists() else []
        assert len(written) == 0

    def test_skipped_message_logged(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-existing",
                type="paper",
                path="papers/h/existing.md",
                doi="10.9999/dup",
            )
        )

        dup_pdf = _make_pdf(folder / "dup.pdf")
        _setup_marker_output(dup_pdf, "# Dup\nDOI: 10.9999/dup.\n")

        with (
            patch("subprocess.run", return_value=_marker_ok()),
            caplog.at_level(logging.INFO, logger="hydrofound.ingestion.paper"),
        ):
            ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert any("skipped" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# ingest_papers_batch — individual failure continues batch
# ---------------------------------------------------------------------------


class TestBatchFailureContinues:
    """A failure on one PDF must not abort the remaining papers."""

    def test_failure_counted_correctly(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        # ok1 and ok2 succeed; fail1 returns non-zero exit code.
        ok1 = _make_pdf(folder / "ok1.pdf")
        _setup_marker_output(ok1, "# OK One (2020)\nDOI: 10.1234/ok1year.\n")

        fail1 = _make_pdf(folder / "fail1.pdf")
        _setup_marker_output(fail1, "# Fail One\n")

        ok2 = _make_pdf(folder / "ok2.pdf")
        _setup_marker_output(ok2, "# OK Two (2021)\nDOI: 10.1234/ok2year.\n")

        def _side_effect(cmd, **kwargs):
            # Fail when called for fail1.pdf
            if "fail1" in str(cmd):
                return _marker_fail()
            return _marker_ok()

        with patch("subprocess.run", side_effect=_side_effect):
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.failed == 1
        assert result.ingested == 2
        assert result.skipped == 0

    def test_failed_path_recorded_in_errors(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        fail_pdf = _make_pdf(folder / "fail.pdf")
        _setup_marker_output(fail_pdf, "# Fail\n")

        with patch("subprocess.run", return_value=_marker_fail()):
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert fail_pdf in result.errors
        assert len(result.errors[fail_pdf]) > 0

    def test_other_papers_still_ingested_after_failure(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        ok_pdf = _make_pdf(folder / "ok.pdf")
        _setup_marker_output(ok_pdf, "# OK Paper (2022)\nDOI: 10.1234/ok2022.\n")

        fail_pdf = _make_pdf(folder / "fail.pdf")
        _setup_marker_output(fail_pdf, "# Fail\n")

        def _side_effect(cmd, **kwargs):
            if "fail" in str(cmd):
                return _marker_fail()
            return _marker_ok()

        with patch("subprocess.run", side_effect=_side_effect):
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.ingested == 1
        assert result.failed == 1
        catalog = json.loads((kb / "catalog.json").read_text())
        assert len(catalog) == 1


# ---------------------------------------------------------------------------
# ingest_papers_batch — summary report
# ---------------------------------------------------------------------------


class TestBatchSummaryReport:
    """BatchResult __str__ reflects the correct counts."""

    def test_summary_three_ingested_one_skipped_one_failed(
        self, tmp_path: Path
    ) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        # Pre-populate one duplicate DOI (must use valid DOI: 10.XXXX/... with 4+ digits).
        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="paper-dup",
                type="paper",
                path="papers/h/dup.md",
                doi="10.9999/dup2024",
            )
        )

        # 3 unique papers
        for i in range(3):
            pdf = _make_pdf(folder / f"ok{i}.pdf")
            _setup_marker_output(
                pdf, f"# OK {i} ({2020 + i})\nDOI: 10.1234/ok{i}year.\n"
            )

        # 1 duplicate
        dup = _make_pdf(folder / "dup.pdf")
        _setup_marker_output(dup, "# Dup Paper (2024)\nDOI: 10.9999/dup2024.\n")

        # 1 failing
        fail = _make_pdf(folder / "fail.pdf")
        _setup_marker_output(fail, "# Fail\n")

        def _side_effect(cmd, **kwargs):
            if "fail" in str(cmd):
                return _marker_fail()
            return _marker_ok()

        with patch("subprocess.run", side_effect=_side_effect):
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.ingested == 3
        assert result.skipped == 1
        assert result.failed == 1
        assert str(result) == "3 ingested, 1 skipped, 1 failed"

    def test_empty_folder_all_zeros(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        with patch("subprocess.run", return_value=_marker_ok()):
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.ingested == 0
        assert result.skipped == 0
        assert result.failed == 0


# ---------------------------------------------------------------------------
# ingest_papers_batch — single reindex at end
# ---------------------------------------------------------------------------


class TestBatchSingleReindex:
    """qmd reindex is issued exactly once after the batch, not per-file."""

    def test_reindex_called_once_after_batch(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        for i in range(3):
            pdf = _make_pdf(folder / f"p{i}.pdf")
            _setup_marker_output(
                pdf, f"# Paper {i} ({2020 + i})\nDOI: 10.9999/p{i}reindex.\n"
            )

        marker_result = _marker_ok()
        qmd_result = MagicMock()
        qmd_result.returncode = 0

        with (
            patch("subprocess.run", return_value=marker_result) as mock_run,
            patch("shutil.which", return_value="/usr/bin/qmd"),
        ):
            ingest_papers_batch(folder, "hydrology", kb, cfg)

        # 3 marker calls + 1 qmd reindex = 4 total
        assert mock_run.call_count == 4
        qmd_calls = [c for c in mock_run.call_args_list if "qmd" in str(c)]
        assert len(qmd_calls) == 1

    def test_reindex_not_called_when_nothing_ingested(self, tmp_path: Path) -> None:
        """No reindex when the batch ingests zero papers (all skipped or failed)."""
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        # All PDFs fail.
        fail = _make_pdf(folder / "fail.pdf")
        _setup_marker_output(fail, "# Fail\n")

        with (
            patch("subprocess.run", return_value=_marker_fail()) as mock_run,
            patch("shutil.which", return_value="/usr/bin/qmd"),
        ):
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.ingested == 0
        # Only the Marker call — no qmd call.
        qmd_calls = [c for c in mock_run.call_args_list if "qmd" in str(c)]
        assert len(qmd_calls) == 0

    def test_reindex_not_called_per_file(self, tmp_path: Path) -> None:
        """Verify reindex is called at most once even for N > 1 papers."""
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        n = 5
        for i in range(n):
            pdf = _make_pdf(folder / f"paper_{i}.pdf")
            _setup_marker_output(pdf, f"# Paper {i} ({2020 + i})\nDOI: 10.99/{i}.\n")

        with (
            patch("subprocess.run", return_value=_marker_ok()) as mock_run,
            patch("shutil.which", return_value="/usr/bin/qmd"),
        ):
            ingest_papers_batch(folder, "hydrology", kb, cfg)

        qmd_calls = [c for c in mock_run.call_args_list if "qmd" in str(c)]
        assert len(qmd_calls) == 1, f"Expected 1 qmd reindex call, got {len(qmd_calls)}"


# ---------------------------------------------------------------------------
# ingest_papers_batch — recursive walk
# ---------------------------------------------------------------------------


class TestBatchRecursiveWalk:
    """PDFs in subdirectories are discovered."""

    def test_discovers_pdfs_in_subdirs(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        cfg = _make_config(tmp_path)

        sub = folder / "sub"
        sub.mkdir(parents=True)

        top_pdf = _make_pdf(folder / "top.pdf")
        _setup_marker_output(top_pdf, "# Top (2020)\nDOI: 10.1234/top2020.\n")

        sub_pdf = _make_pdf(sub / "sub.pdf")
        _setup_marker_output(sub_pdf, "# Sub (2021)\nDOI: 10.1234/sub2021.\n")

        with patch("subprocess.run", return_value=_marker_ok()):
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.ingested == 2
