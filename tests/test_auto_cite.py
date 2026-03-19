"""Tests for auto-cite — KB search + external auto-ingest."""

from __future__ import annotations

from pathlib import Path

import frontmatter as fm_lib
from typer.testing import CliRunner

from papermind.auto_cite import auto_cite, format_auto_cite
from papermind.catalog.index import CatalogEntry, CatalogIndex
from papermind.cli.main import app

runner = CliRunner()


def _make_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    kb.mkdir(parents=True)
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")

    catalog = CatalogIndex(kb)
    paper_dir = kb / "papers" / "hydrology" / "swat-review"
    paper_dir.mkdir(parents=True)
    post = fm_lib.Post("# SWAT+ Review\n\nContent.\n")
    post.metadata = {
        "type": "paper",
        "id": "paper-swat-review",
        "title": "SWAT+ Model Review",
        "topic": "hydrology",
        "doi": "10.1234/swat-review",
    }
    (paper_dir / "paper.md").write_text(fm_lib.dumps(post))
    catalog.add(
        CatalogEntry(
            id="paper-swat-review",
            type="paper",
            path="papers/hydrology/swat-review/paper.md",
            title="SWAT+ Model Review",
            topic="hydrology",
            doi="10.1234/swat-review",
        )
    )
    return kb


class TestAutoCite:
    def test_returns_result_structure(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        # min_kb_results=0 so it doesn't try external
        result = auto_cite(
            "SWAT model",
            kb,
            min_kb_results=0,
            max_results=3,
        )
        assert result.claim == "SWAT model"
        assert isinstance(result.kb_refs, list)
        assert isinstance(result.newly_ingested, list)
        assert isinstance(result.external_only, list)
        assert result.total >= 0

    def test_kb_only_no_external(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        result = auto_cite(
            "SWAT model",
            kb,
            min_kb_results=0,  # don't trigger external
        )
        assert result.newly_ingested == []
        assert result.external_only == []

    def test_format_output(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        result = auto_cite("SWAT", kb, min_kb_results=0)
        text = format_auto_cite(result)
        assert "Claim:" in text
        assert "Total:" in text


class TestAutoCiteCLI:
    def test_auto_cite_no_external(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "auto-cite",
                "SWAT model review",
                "--no-external",
            ],
        )
        assert result.exit_code == 0

    def test_auto_cite_basic(self, tmp_path: Path) -> None:
        """Basic auto-cite (may try external but should not crash)."""
        kb = _make_kb(tmp_path)
        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "auto-cite",
                "SWAT calibration",
                "--no-external",
            ],
        )
        assert result.exit_code == 0
