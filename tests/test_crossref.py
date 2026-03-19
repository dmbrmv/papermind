"""Tests for cross-reference (keyword similarity) feature."""

from __future__ import annotations

from pathlib import Path

import frontmatter as fm_lib
from typer.testing import CliRunner

from papermind.cli.main import app
from papermind.crossref import backfill_cross_refs, compute_cross_refs

runner = CliRunner()


def _make_kb_with_tagged_papers(tmp_path: Path) -> Path:
    """Create a KB with papers that have overlapping tags."""
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")

    papers_data = [
        ("paper-swat-cal", "SWAT Calibration", ["calibration", "swat", "sensitivity"]),
        ("paper-swat-val", "SWAT Validation", ["validation", "swat", "nse"]),
        ("paper-lstm-hydro", "LSTM Hydrology", ["lstm", "deep_learning", "prediction"]),
        ("paper-cnn-hydro", "CNN Hydrology", ["cnn", "deep_learning", "prediction"]),
        ("paper-solo", "Solo Paper", []),  # no tags — should be excluded
    ]

    from papermind.catalog.index import CatalogEntry, CatalogIndex

    catalog = CatalogIndex(kb)

    for pid, title, tags in papers_data:
        slug = pid.removeprefix("paper-")
        paper_dir = kb / "papers" / "hydrology" / slug
        paper_dir.mkdir(parents=True)

        post = fm_lib.Post(f"# {title}\n\nContent.\n")
        post.metadata = {
            "type": "paper",
            "id": pid,
            "title": title,
            "topic": "hydrology",
            "tags": tags,
        }
        (paper_dir / "paper.md").write_text(fm_lib.dumps(post))

        catalog.add(
            CatalogEntry(
                id=pid,
                type="paper",
                path=f"papers/hydrology/{slug}/paper.md",
                title=title,
                topic="hydrology",
                tags=tags,
            )
        )

    return kb


class TestComputeCrossRefs:
    """Test the cross-reference computation engine."""

    def test_finds_related_papers(self, tmp_path: Path) -> None:
        kb = _make_kb_with_tagged_papers(tmp_path)
        refs = compute_cross_refs(kb, min_score=0.1)

        # SWAT cal and SWAT val share "swat" + "hydrology" topic
        assert "paper-swat-cal" in refs
        related_ids = [r[0] for r in refs["paper-swat-cal"]]
        assert "paper-swat-val" in related_ids

    def test_ml_papers_related(self, tmp_path: Path) -> None:
        kb = _make_kb_with_tagged_papers(tmp_path)
        refs = compute_cross_refs(kb, min_score=0.1)

        # LSTM and CNN share "deep_learning" + "prediction" + "hydrology"
        assert "paper-lstm-hydro" in refs
        related_ids = [r[0] for r in refs["paper-lstm-hydro"]]
        assert "paper-cnn-hydro" in related_ids

    def test_no_tags_low_connectivity(self, tmp_path: Path) -> None:
        kb = _make_kb_with_tagged_papers(tmp_path)
        refs = compute_cross_refs(kb, min_score=0.1)

        # Solo paper has no explicit tags (only implicit topic tag),
        # so its connections should be weaker than tagged papers
        if "paper-solo" in refs:
            solo_max_score = max(s for _, s in refs["paper-solo"])
            lstm_max_score = max(s for _, s in refs["paper-lstm-hydro"])
            assert solo_max_score <= lstm_max_score

    def test_min_score_filtering(self, tmp_path: Path) -> None:
        kb = _make_kb_with_tagged_papers(tmp_path)

        # Very high threshold should reduce results
        strict = compute_cross_refs(kb, min_score=0.8)
        loose = compute_cross_refs(kb, min_score=0.1)

        strict_links = sum(len(v) for v in strict.values())
        loose_links = sum(len(v) for v in loose.values())
        assert strict_links <= loose_links

    def test_empty_kb(self, tmp_path: Path) -> None:
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / ".papermind").mkdir()
        refs = compute_cross_refs(kb)
        assert refs == {}


class TestBackfillCrossRefs:
    """Test writing cross-refs to frontmatter."""

    def test_backfill_writes_keyword_related(self, tmp_path: Path) -> None:
        kb = _make_kb_with_tagged_papers(tmp_path)
        updated = backfill_cross_refs(kb, min_score=0.1)

        assert updated > 0

        # Check one paper has keyword_related in frontmatter
        lstm_paper = kb / "papers" / "hydrology" / "lstm-hydro" / "paper.md"
        post = fm_lib.load(lstm_paper)
        assert "keyword_related" in post.metadata
        assert isinstance(post.metadata["keyword_related"], list)


class TestCrossrefCLI:
    """Test CLI integration."""

    def test_crossref_preview(self, tmp_path: Path) -> None:
        kb = _make_kb_with_tagged_papers(tmp_path)
        result = runner.invoke(app, ["--kb", str(kb), "crossref"])
        assert result.exit_code == 0
        assert "cross-reference" in result.output

    def test_crossref_save(self, tmp_path: Path) -> None:
        kb = _make_kb_with_tagged_papers(tmp_path)
        result = runner.invoke(app, ["--kb", str(kb), "crossref", "--save"])
        assert result.exit_code == 0
        assert "Updated" in result.output
