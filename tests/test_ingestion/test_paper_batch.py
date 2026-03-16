"""Tests for batch paper ingestion — folder walk, dedup, single reindex."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from papermind.catalog.index import CatalogEntry, CatalogIndex
from papermind.config import PaperMindConfig
from papermind.ingestion.paper import BatchResult, ingest_papers_batch

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

PDF_MAGIC = b"%PDF-1.4\n" + b"x" * 2048  # passes validate_pdf

# Map of pdf stem → markdown content, set per test
_MD_STORE: dict[str, str] = {}


def _make_pdf(path: Path) -> Path:
    path.write_bytes(PDF_MAGIC)
    return path


def _make_config(tmp_path: Path) -> PaperMindConfig:
    return PaperMindConfig(base_path=tmp_path)


def _make_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")
    return kb


def _glm_from_store(path, model_name="zai-org/GLM-OCR", dpi=150):
    """Mock GLM-OCR that returns markdown from _MD_STORE by PDF stem."""
    stem = Path(path).stem
    md = _MD_STORE.get(stem)
    if md is None:
        raise RuntimeError(f"No mock content for {stem}")
    return md


def _mock_glm():
    """Patch GLM-OCR to use _MD_STORE."""
    return patch(
        "papermind.ingestion.glm_ocr.convert_pdf_glm",
        side_effect=_glm_from_store,
    )


def _setup_batch(folder: Path, papers: list[tuple[str, str]]) -> None:
    """Create fake PDFs and register their markdown content in _MD_STORE."""
    _MD_STORE.clear()
    for stem, md in papers:
        _make_pdf(folder / f"{stem}.pdf")
        _MD_STORE[stem] = md


# ---------------------------------------------------------------------------
# BatchResult
# ---------------------------------------------------------------------------


class TestBatchResult:
    def test_initial_counts_are_zero(self) -> None:
        r = BatchResult()
        assert r.ingested == 0 and r.skipped == 0 and r.failed == 0

    def test_str_format(self) -> None:
        r = BatchResult()
        r.ingested, r.skipped, r.failed = 3, 1, 1
        assert str(r) == "3 ingested, 1 skipped, 1 failed"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestBatchAllSucceed:
    def test_all_three_ingested(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        _setup_batch(
            folder,
            [
                ("paper_a", "# Paper A (2020)\nDOI: 10.1111/a.2020.\n"),
                ("paper_b", "# Paper B (2021)\nDOI: 10.1111/b.2021.\n"),
                ("paper_c", "# Paper C (2022)\nDOI: 10.1111/c.2022.\n"),
            ],
        )

        with _mock_glm():
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.ingested == 3 and result.skipped == 0 and result.failed == 0

    def test_catalog_has_three_entries(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        _setup_batch(
            folder,
            [
                (f"paper_{i}", f"# Paper {i} ({2020 + i})\nDOI: 10.1234/p{i}.\n")
                for i in range(3)
            ],
        )

        with _mock_glm():
            ingest_papers_batch(folder, "hydrology", kb, cfg)

        catalog = json.loads((kb / "catalog.json").read_text())
        assert len(catalog) == 3

    def test_markdown_files_written_to_topic_dir(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        _setup_batch(
            folder,
            [
                (f"doc_{i}", f"# Doc {i} ({2019 + i})\nDOI: 10.2/{i}.\n")
                for i in range(2)
            ],
        )

        with _mock_glm():
            ingest_papers_batch(folder, "swat", kb, cfg)

        topic_dir = kb / "papers" / "swat"
        assert topic_dir.is_dir()
        assert len(list(topic_dir.rglob("paper.md"))) == 2


# ---------------------------------------------------------------------------
# Duplicate DOI skip
# ---------------------------------------------------------------------------


class TestBatchDuplicateSkip:
    def test_duplicate_counted_as_skipped(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        CatalogIndex(kb).add(
            CatalogEntry(
                id="paper-existing",
                type="paper",
                path="papers/hydrology/existing.md",
                doi="10.9999/dup",
            )
        )

        _setup_batch(
            folder,
            [
                ("dup", "# Dup Paper (2021)\nDOI: 10.9999/dup.\n"),
                ("new", "# New Paper (2022)\nDOI: 10.9999/new.\n"),
            ],
        )

        with _mock_glm():
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.skipped == 1 and result.ingested == 1

    def test_duplicate_not_written_to_disk(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        CatalogIndex(kb).add(
            CatalogEntry(
                id="paper-existing",
                type="paper",
                path="papers/hydrology/existing.md",
                doi="10.9999/dup",
            )
        )

        _setup_batch(folder, [("dup", "# Dup Paper\nDOI: 10.9999/dup.\n")])

        with _mock_glm():
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

        CatalogIndex(kb).add(
            CatalogEntry(
                id="paper-existing",
                type="paper",
                path="papers/h/existing.md",
                doi="10.9999/dup",
            )
        )

        _setup_batch(folder, [("dup", "# Dup\nDOI: 10.9999/dup.\n")])

        with (
            _mock_glm(),
            caplog.at_level(logging.INFO, logger="papermind.ingestion.paper"),
        ):
            ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert any("skipped" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Failure continues batch
# ---------------------------------------------------------------------------


class TestBatchFailureContinues:
    def test_failure_counted_correctly(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        _setup_batch(
            folder,
            [
                ("ok1", "# OK One (2020)\nDOI: 10.1234/ok1.\n"),
                ("ok2", "# OK Two (2021)\nDOI: 10.1234/ok2.\n"),
            ],
        )
        # fail1 — not in store, will raise RuntimeError
        _make_pdf(folder / "fail1.pdf")

        with _mock_glm():
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.failed == 1 and result.ingested == 2

    def test_failed_path_recorded_in_errors(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        fail_pdf = _make_pdf(folder / "fail.pdf")
        _MD_STORE.clear()  # no content → RuntimeError

        with _mock_glm():
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert fail_pdf in result.errors

    def test_other_papers_still_ingested_after_failure(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        _setup_batch(
            folder,
            [
                ("ok", "# OK Paper (2022)\nDOI: 10.1234/ok2022.\n"),
            ],
        )
        _make_pdf(folder / "fail.pdf")  # not in store → fails

        with _mock_glm():
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.ingested == 1 and result.failed == 1


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------


class TestBatchSummaryReport:
    def test_summary_three_ingested_one_skipped_one_failed(
        self, tmp_path: Path
    ) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        CatalogIndex(kb).add(
            CatalogEntry(
                id="paper-dup",
                type="paper",
                path="papers/h/dup.md",
                doi="10.9999/dup2024",
            )
        )

        _setup_batch(
            folder,
            [
                (f"ok{i}", f"# OK {i} ({2020 + i})\nDOI: 10.1234/ok{i}.\n")
                for i in range(3)
            ],
        )
        # duplicate
        _make_pdf(folder / "dup.pdf")
        _MD_STORE["dup"] = "# Dup Paper (2024)\nDOI: 10.9999/dup2024.\n"
        # failure
        _make_pdf(folder / "fail.pdf")  # not in store

        with _mock_glm():
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

        _MD_STORE.clear()

        with _mock_glm():
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.ingested == 0 and result.skipped == 0 and result.failed == 0


# ---------------------------------------------------------------------------
# Single reindex at end
# ---------------------------------------------------------------------------


class TestBatchSingleReindex:
    def test_reindex_called_once_after_batch(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        _setup_batch(
            folder,
            [
                (f"p{i}", f"# Paper {i} ({2020 + i})\nDOI: 10.9999/p{i}.\n")
                for i in range(3)
            ],
        )

        with (
            _mock_glm(),
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/qmd"),
        ):
            ingest_papers_batch(folder, "hydrology", kb, cfg)

        # Only qmd reindex call — no marker calls
        assert mock_run.call_count == 1
        qmd_cmd = mock_run.call_args[0][0]
        assert "qmd" in qmd_cmd[0]

    def test_reindex_not_called_when_nothing_ingested(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        _make_pdf(folder / "fail.pdf")
        _MD_STORE.clear()

        with (
            _mock_glm(),
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/qmd"),
        ):
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.ingested == 0
        mock_run.assert_not_called()

    def test_reindex_not_called_per_file(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        folder.mkdir()
        cfg = _make_config(tmp_path)

        _setup_batch(
            folder,
            [
                (f"paper_{i}", f"# Paper {i} ({2020 + i})\nDOI: 10.99/{i}.\n")
                for i in range(5)
            ],
        )

        with (
            _mock_glm(),
            patch("subprocess.run") as mock_run,
            patch("shutil.which", return_value="/usr/bin/qmd"),
        ):
            ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert mock_run.call_count == 1  # exactly 1 qmd call


# ---------------------------------------------------------------------------
# Recursive walk
# ---------------------------------------------------------------------------


class TestBatchRecursiveWalk:
    def test_discovers_pdfs_in_subdirs(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        folder = tmp_path / "pdfs"
        sub = folder / "sub"
        sub.mkdir(parents=True)
        cfg = _make_config(tmp_path)

        _make_pdf(folder / "top.pdf")
        _make_pdf(sub / "sub.pdf")
        _MD_STORE.clear()
        _MD_STORE["top"] = "# Top (2020)\nDOI: 10.1234/top2020.\n"
        _MD_STORE["sub"] = "# Sub (2021)\nDOI: 10.1234/sub2021.\n"

        with _mock_glm():
            result = ingest_papers_batch(folder, "hydrology", kb, cfg)

        assert result.ingested == 2
