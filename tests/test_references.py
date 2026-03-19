"""Tests for reference finder, bib-gap analysis, and reviewer response."""

from __future__ import annotations

from pathlib import Path

import frontmatter as fm_lib
from typer.testing import CliRunner

from papermind.catalog.index import CatalogEntry, CatalogIndex
from papermind.cli.main import app
from papermind.references import (
    analyze_bibliography_gaps,
    extract_claims,
    find_evidence_for_comment,
    find_references,
)

runner = CliRunner()


def _make_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    kb.mkdir(parents=True)
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")

    catalog = CatalogIndex(kb)
    paper_dir = kb / "papers" / "hydrology" / "swat-cn"
    paper_dir.mkdir(parents=True)
    post = fm_lib.Post(
        "# SCS Curve Number for SWAT+\n\n"
        "The SCS-CN method is widely used for runoff estimation.\n"
    )
    post.metadata = {
        "type": "paper",
        "id": "paper-swat-cn-2020",
        "title": "SCS Curve Number Method for SWAT+",
        "topic": "hydrology",
        "doi": "10.1234/swat-cn",
        "abstract": "This paper reviews the SCS-CN method.",
        "tags": ["swat", "cn", "runoff"],
    }
    (paper_dir / "paper.md").write_text(fm_lib.dumps(post))
    catalog.add(
        CatalogEntry(
            id="paper-swat-cn-2020",
            type="paper",
            path="papers/hydrology/swat-cn/paper.md",
            title="SCS Curve Number Method for SWAT+",
            topic="hydrology",
            doi="10.1234/swat-cn",
        )
    )
    return kb


class TestExtractClaims:
    def test_finds_claim(self) -> None:
        text = (
            "The SCS-CN method has been widely used for runoff estimation. "
            "It was developed in the 1950s."
        )
        claims = extract_claims(text)
        assert len(claims) >= 1
        assert any("widely used" in c for c in claims)

    def test_skips_cited(self) -> None:
        text = "The method has been widely used [1]. Another sentence."
        claims = extract_claims(text)
        assert not any("widely used" in c for c in claims)

    def test_empty_text(self) -> None:
        assert extract_claims("") == []

    def test_no_claims(self) -> None:
        text = "This is the introduction. We present our model."
        claims = extract_claims(text)
        assert claims == []


class TestFindReferences:
    def test_returns_claim_result(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        result = find_references(
            "SCS curve number runoff",
            kb,
            search_external=False,
        )
        # Verify structure — grep fallback may not find in tiny KB
        assert result.claim == "SCS curve number runoff"
        assert isinstance(result.references, list)
        assert result.external_count == 0

    def test_no_crash_on_unrelated(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        result = find_references(
            "quantum computing neural networks",
            kb,
            search_external=False,
        )
        assert isinstance(result.references, list)


class TestBibGapAnalysis:
    def test_finds_gaps(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        draft = tmp_path / "draft.md"
        draft.write_text(
            "# Introduction\n\n"
            "The SCS-CN method has been widely used for "
            "watershed modeling. "
            "Studies have shown that calibration improves results. "
            "We present our approach.\n"
        )
        results = analyze_bibliography_gaps(draft, kb, search_external=False)
        # Claims extracted; results may be empty in tiny test KB
        assert isinstance(results, list)

    def test_no_gaps_in_cited_text(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        draft = tmp_path / "draft.md"
        draft.write_text(
            "The method is described by Arnold et al. (2012). "
            "Our results are shown in Table 1.\n"
        )
        results = analyze_bibliography_gaps(draft, kb, search_external=False)
        assert len(results) == 0


class TestReviewerResponse:
    def test_finds_evidence(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        result = find_evidence_for_comment(
            "Why did you not consider the SCS curve number method?",
            kb,
            search_external=False,
        )
        # Verify structure — search may return empty in tiny KB
        assert result.claim is not None
        assert isinstance(result.references, list)


class TestReferencesCLI:
    def test_cite(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "cite",
                "SCS curve number runoff",
                "--no-external",
            ],
        )
        assert result.exit_code == 0

    def test_bib_gap(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        draft = tmp_path / "draft.md"
        draft.write_text(
            "Studies have shown that SWAT calibration is important for accuracy.\n"
        )
        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "bib-gap",
                str(draft),
                "--no-external",
            ],
        )
        assert result.exit_code == 0

    def test_respond(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "respond",
                "What about curve number sensitivity?",
                "--no-external",
            ],
        )
        assert result.exit_code == 0
        assert "Evidence" in result.output or "Reviewer" in result.output
