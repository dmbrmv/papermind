"""Tests for papermind audit commands."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import frontmatter
from typer.testing import CliRunner

from papermind.cli.main import app

runner = CliRunner()


def _make_kb_with_verified(tmp_path: Path) -> Path:
    """Create a KB with papers in various verification states."""
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])

    papers_dir = kb / "papers" / "hydrology"
    papers_dir.mkdir(parents=True)

    # Paper 1: never verified
    d1 = papers_dir / "paper-a"
    d1.mkdir()
    post1 = frontmatter.Post("# Paper A")
    post1.metadata = {
        "type": "paper",
        "id": "paper-a",
        "title": "Paper A",
        "topic": "hydrology",
    }
    (d1 / "paper.md").write_text(frontmatter.dumps(post1))

    # Paper 2: verified recently
    d2 = papers_dir / "paper-b"
    d2.mkdir()
    post2 = frontmatter.Post("# Paper B")
    post2.metadata = {
        "type": "paper",
        "id": "paper-b",
        "title": "Paper B",
        "topic": "hydrology",
        "last_verified": date.today().isoformat(),
    }
    (d2 / "paper.md").write_text(frontmatter.dumps(post2))

    # Paper 3: verified long ago
    d3 = papers_dir / "paper-c"
    d3.mkdir()
    post3 = frontmatter.Post("# Paper C")
    old_date = (date.today() - timedelta(days=200)).isoformat()
    post3.metadata = {
        "type": "paper",
        "id": "paper-c",
        "title": "Paper C",
        "topic": "hydrology",
        "last_verified": old_date,
    }
    (d3 / "paper.md").write_text(frontmatter.dumps(post3))

    catalog = [
        {
            "id": f"paper-{x}",
            "type": "paper",
            "title": f"Paper {x.upper()}",
            "path": f"papers/hydrology/paper-{x}/paper.md",
            "topic": "hydrology",
        }
        for x in ["a", "b", "c"]
    ]
    (kb / "catalog.json").write_text(json.dumps(catalog))
    return kb


def test_audit_stale_finds_unverified(tmp_path: Path) -> None:
    """audit stale should flag papers without last_verified."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "stale", "--days", "90"])
    assert result.exit_code == 0
    assert "never verified" in result.output
    assert "paper-a" in result.output


def test_audit_stale_finds_old_verified(tmp_path: Path) -> None:
    """audit stale should flag papers verified >90 days ago."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "stale", "--days", "90"])
    assert "paper-c" in result.output


def test_audit_stale_excludes_recent(tmp_path: Path) -> None:
    """Recently verified papers should not be flagged."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "stale", "--days", "90"])
    assert "paper-b" not in result.output


def test_audit_verify_marks_paper(tmp_path: Path) -> None:
    """audit verify should set last_verified to today."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "verify", "paper-a"])
    assert result.exit_code == 0
    assert "Verified" in result.output

    # Check frontmatter was updated
    post = frontmatter.load(kb / "papers" / "hydrology" / "paper-a" / "paper.md")
    assert post.metadata["last_verified"] == date.today().isoformat()


def test_audit_verify_with_note(tmp_path: Path) -> None:
    """audit verify --note should store the note."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(
        app,
        [
            "--kb",
            str(kb),
            "audit",
            "verify",
            "paper-a",
            "--note",
            "Checked OK",
        ],
    )
    assert result.exit_code == 0

    post = frontmatter.load(kb / "papers" / "hydrology" / "paper-a" / "paper.md")
    assert post.metadata["verification_note"] == "Checked OK"


def test_audit_verify_not_found(tmp_path: Path) -> None:
    """audit verify for unknown paper should fail."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "verify", "nonexistent"])
    assert result.exit_code == 1
