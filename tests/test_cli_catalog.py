"""Tests for catalog CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from hydrofound.cli.main import app

runner = CliRunner()


def _init_kb_with_entries(tmp_path: Path) -> Path:
    """Create a KB with some catalog entries."""
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])

    # Add a paper entry manually (simulating post-ingest state)
    import frontmatter

    papers_dir = kb / "papers" / "hydrology"
    papers_dir.mkdir(parents=True)
    post = frontmatter.Post("# Test Paper\n\nSome content.")
    post.metadata = {
        "id": "paper-test-2024",
        "type": "paper",
        "title": "Test Paper",
        "topic": "hydrology",
    }
    (papers_dir / "test-2024.md").write_text(frontmatter.dumps(post))

    # Update catalog.json
    catalog_data = [
        {
            "id": "paper-test-2024",
            "type": "paper",
            "title": "Test Paper",
            "path": "papers/hydrology/test-2024.md",
            "topic": "hydrology",
        }
    ]
    (kb / "catalog.json").write_text(json.dumps(catalog_data, indent=2))

    # Regenerate catalog.md to reflect the new entries
    from hydrofound.catalog.index import CatalogIndex
    from hydrofound.catalog.render import render_catalog_md

    index = CatalogIndex(kb)
    (kb / "catalog.md").write_text(render_catalog_md(index.entries))

    return kb


def test_catalog_show(tmp_path: Path) -> None:
    kb = _init_kb_with_entries(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "catalog", "show"])
    assert result.exit_code == 0
    assert "Test Paper" in result.output or "1 papers" in result.output


def test_catalog_stats(tmp_path: Path) -> None:
    kb = _init_kb_with_entries(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "catalog", "stats"])
    assert result.exit_code == 0
    assert "1" in result.output  # 1 paper


def test_remove_entry(tmp_path: Path) -> None:
    kb = _init_kb_with_entries(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "remove", "paper-test-2024"])
    assert result.exit_code == 0
    # Verify removed from catalog
    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 0
    # Verify file deleted
    assert not (kb / "papers" / "hydrology" / "test-2024.md").exists()


def test_remove_nonexistent(tmp_path: Path) -> None:
    kb = _init_kb_with_entries(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "remove", "nonexistent-id"])
    assert result.exit_code != 0
