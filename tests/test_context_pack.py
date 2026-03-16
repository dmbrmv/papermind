"""Tests for papermind context-pack command."""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter
from typer.testing import CliRunner

from papermind.cli.main import app

runner = CliRunner()


def _make_kb_with_papers(tmp_path: Path) -> Path:
    """Create a KB with papers that have rich metadata."""
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])

    papers_dir = kb / "papers" / "hydrology"
    papers_dir.mkdir(parents=True)

    for i, (title, doi, abstract) in enumerate(
        [
            (
                "SWAT Calibration Guide",
                "10.1/swat",
                "A guide to calibrating SWAT models.",
            ),
            (
                "LSTM for Streamflow",
                "10.1/lstm",
                "Using LSTM networks for streamflow prediction.",
            ),
        ]
    ):
        slug = f"paper-{i}"
        d = papers_dir / slug
        d.mkdir()
        post = frontmatter.Post(f"# {title}\n\nContent.")
        post.metadata = {
            "type": "paper",
            "id": f"paper-{slug}",
            "title": title,
            "topic": "hydrology",
            "doi": doi,
            "abstract": abstract,
            "cites": [f"10.1/ref-{i}"],
            "cited_by": [f"10.1/citer-{i}"],
            "tags": ["swat", "calibration"] if i == 0 else ["lstm"],
        }
        (d / "paper.md").write_text(frontmatter.dumps(post))

    catalog = [
        {
            "id": f"paper-paper-{i}",
            "type": "paper",
            "title": t,
            "path": f"papers/hydrology/paper-{i}/paper.md",
            "topic": "hydrology",
            "doi": d,
        }
        for i, (t, d, _) in enumerate(
            [
                ("SWAT Calibration Guide", "10.1/swat", ""),
                ("LSTM for Streamflow", "10.1/lstm", ""),
            ]
        )
    ]
    (kb / "catalog.json").write_text(json.dumps(catalog))
    return kb


def test_context_pack_generates_output(tmp_path: Path) -> None:
    """context-pack should produce a markdown briefing."""
    kb = _make_kb_with_papers(tmp_path)
    result = runner.invoke(
        app,
        ["--kb", str(kb), "context-pack", "hydrology", "--max-tokens", "2000"],
    )
    assert result.exit_code == 0
    assert "PaperMind Briefing" in result.output
    assert "SWAT" in result.output or "LSTM" in result.output


def test_context_pack_respects_budget(tmp_path: Path) -> None:
    """Small budget should truncate output."""
    kb = _make_kb_with_papers(tmp_path)
    result = runner.invoke(
        app,
        ["--kb", str(kb), "context-pack", "hydrology", "--max-tokens", "50"],
    )
    assert result.exit_code == 0
    # Very small budget — should truncate
    assert len(result.output) < 1000


def test_context_pack_empty_topic(tmp_path: Path) -> None:
    """Non-existent topic should show message."""
    kb = _make_kb_with_papers(tmp_path)
    result = runner.invoke(
        app,
        ["--kb", str(kb), "context-pack", "physics"],
    )
    assert result.exit_code == 0
    assert "No entries" in result.output


def test_context_pack_to_file(tmp_path: Path) -> None:
    """--output should write to file."""
    kb = _make_kb_with_papers(tmp_path)
    out = tmp_path / "briefing.md"
    result = runner.invoke(
        app,
        [
            "--kb",
            str(kb),
            "context-pack",
            "hydrology",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert out.exists()
    assert "PaperMind Briefing" in out.read_text()
