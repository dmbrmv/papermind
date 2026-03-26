"""Tests for the papermind related CLI command."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest
from typer.testing import CliRunner

from papermind.cli.main import app
from papermind.cli.related import (
    _build_doi_index,
    _find_paper_frontmatter,
    _find_reverse_links,
    _resolve_paper_frontmatter,
)

runner = CliRunner()


@pytest.fixture()
def kb_with_citations(tmp_path: Path) -> Path:
    """Create a KB with papers that have citation relationships."""
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()
    (kb / ".papermind" / "config.toml").write_text("")

    papers_dir = kb / "papers" / "hydrology"
    papers_dir.mkdir(parents=True)

    # Paper A cites B and C
    post_a = frontmatter.Post("Content of paper A")
    post_a.metadata = {
        "type": "paper",
        "id": "paper-a-2023",
        "title": "Paper A: Assessment of SWAT+",
        "doi": "10.1/A",
        "cites": ["10.1/B", "10.1/C", "10.1/external"],
        "cited_by": ["10.1/D"],
    }
    (papers_dir / "paper-a.md").write_text(frontmatter.dumps(post_a))

    # Paper B (referenced by A)
    post_b = frontmatter.Post("Content of paper B")
    post_b.metadata = {
        "type": "paper",
        "id": "paper-b-2022",
        "title": "Paper B: Hydrological Modeling",
        "doi": "10.1/B",
        "cites": [],
        "cited_by": ["10.1/A"],
    }
    (papers_dir / "paper-b.md").write_text(frontmatter.dumps(post_b))

    # Paper C (referenced by A, no citation data itself)
    post_c = frontmatter.Post("Content of paper C")
    post_c.metadata = {
        "type": "paper",
        "id": "paper-c-2021",
        "title": "Paper C: Climate Data",
        "doi": "10.1/C",
    }
    (papers_dir / "paper-c.md").write_text(frontmatter.dumps(post_c))

    # Paper D (cites A)
    post_d = frontmatter.Post("Content of paper D")
    post_d.metadata = {
        "type": "paper",
        "id": "paper-d-2024",
        "title": "Paper D: Follow-up Study",
        "doi": "10.1/D",
        "cites": ["10.1/A"],
        "cited_by": [],
    }
    (papers_dir / "paper-d.md").write_text(frontmatter.dumps(post_d))

    # Write catalog.json
    import json

    catalog = [
        {
            "id": "paper-a-2023",
            "type": "paper",
            "path": "papers/hydrology/paper-a.md",
            "title": "Paper A",
            "doi": "10.1/A",
        },
        {
            "id": "paper-b-2022",
            "type": "paper",
            "path": "papers/hydrology/paper-b.md",
            "title": "Paper B",
            "doi": "10.1/B",
        },
        {
            "id": "paper-c-2021",
            "type": "paper",
            "path": "papers/hydrology/paper-c.md",
            "title": "Paper C",
            "doi": "10.1/C",
        },
        {
            "id": "paper-d-2024",
            "type": "paper",
            "path": "papers/hydrology/paper-d.md",
            "title": "Paper D",
            "doi": "10.1/D",
        },
    ]
    (kb / "catalog.json").write_text(json.dumps(catalog))

    return kb


class TestFindPaperFrontmatter:
    """Tests for _find_paper_frontmatter helper."""

    def test_finds_existing_paper(self, kb_with_citations: Path) -> None:
        fm = _find_paper_frontmatter(kb_with_citations, "paper-a-2023")
        assert fm is not None
        assert fm["doi"] == "10.1/A"

    def test_returns_none_for_missing(self, kb_with_citations: Path) -> None:
        fm = _find_paper_frontmatter(kb_with_citations, "paper-nonexistent")
        assert fm is None


class TestBuildDoiIndex:
    """Tests for _build_doi_index helper."""

    def test_indexes_all_papers(self, kb_with_citations: Path) -> None:
        index = _build_doi_index(kb_with_citations)
        assert "10.1/A" in index
        assert "10.1/B" in index
        assert "10.1/C" in index
        assert "10.1/D" in index

    def test_index_values_contain_id_and_title(self, kb_with_citations: Path) -> None:
        index = _build_doi_index(kb_with_citations)
        pid, title = index["10.1/A"]
        assert pid == "paper-a-2023"
        assert "Paper A" in title


class TestResolvePaperFrontmatter:
    """Tests for id/path/doi paper resolution."""

    def test_resolves_by_relative_path(self, kb_with_citations: Path) -> None:
        fm, matched_via = _resolve_paper_frontmatter(
            kb_with_citations,
            "papers/hydrology/paper-a.md",
        )
        assert fm is not None
        assert matched_via == "path"
        assert fm["id"] == "paper-a-2023"

    def test_resolves_by_doi(self, kb_with_citations: Path) -> None:
        fm, matched_via = _resolve_paper_frontmatter(kb_with_citations, "10.1/A")
        assert fm is not None
        assert matched_via == "doi"
        assert fm["id"] == "paper-a-2023"


class TestFindReverseLinks:
    """Tests for _find_reverse_links helper."""

    def test_finds_papers_that_cite_target(self, kb_with_citations: Path) -> None:
        refs, citers = _find_reverse_links(kb_with_citations, "10.1/A")
        citer_dois = [doi for doi, _, _ in citers]
        assert "10.1/D" in citer_dois

    def test_finds_papers_cited_by_target(self, kb_with_citations: Path) -> None:
        refs, citers = _find_reverse_links(kb_with_citations, "10.1/A")
        ref_dois = [doi for doi, _, _ in refs]
        # Paper B has cited_by: [10.1/A] — so B is a ref for A
        assert "10.1/B" in ref_dois

    def test_empty_doi_returns_nothing(self, kb_with_citations: Path) -> None:
        refs, citers = _find_reverse_links(kb_with_citations, "")
        assert refs == []
        assert citers == []


class TestRelatedCLI:
    """Integration tests for the `papermind related` command."""

    def test_shows_related_papers(self, kb_with_citations: Path) -> None:
        result = runner.invoke(
            app, ["--kb", str(kb_with_citations), "related", "paper-a-2023"]
        )
        assert result.exit_code == 0
        assert "Paper B" in result.output or "paper-b" in result.output
        assert "related paper(s)" in result.output

    def test_paper_not_found(self, kb_with_citations: Path) -> None:
        result = runner.invoke(
            app, ["--kb", str(kb_with_citations), "related", "nonexistent"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_no_citation_data(self, kb_with_citations: Path) -> None:
        result = runner.invoke(
            app, ["--kb", str(kb_with_citations), "related", "paper-c-2021"]
        )
        assert result.exit_code == 0
        assert "No citation data" in result.output

    def test_accepts_relative_path(self, kb_with_citations: Path) -> None:
        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb_with_citations),
                "related",
                "papers/hydrology/paper-a.md",
            ],
        )
        assert result.exit_code == 0
        assert "Resolved via path" in result.output

    def test_accepts_doi(self, kb_with_citations: Path) -> None:
        result = runner.invoke(
            app,
            ["--kb", str(kb_with_citations), "related", "10.1/A"],
        )
        assert result.exit_code == 0
        assert "Resolved via doi" in result.output
