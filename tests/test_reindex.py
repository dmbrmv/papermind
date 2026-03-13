"""Tests for hydrofound reindex command."""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter
from typer.testing import CliRunner

from hydrofound.cli.main import app

runner = CliRunner()


def _init_kb(tmp_path: Path) -> Path:
    """Create a minimal initialized KB."""
    kb = tmp_path / "kb"
    result = runner.invoke(app, ["init", str(kb)])
    assert result.exit_code == 0, result.output
    return kb


def _write_md(kb: Path, rel_path: str, metadata: dict, body: str = "# Content") -> Path:
    """Write a frontmatter .md file inside the KB."""
    target = kb / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body)
    post.metadata = metadata
    target.write_text(frontmatter.dumps(post))
    return target


# ---------------------------------------------------------------------------
# Test 1: reindex rebuilds catalog.json from .md files
# ---------------------------------------------------------------------------


def test_reindex_rebuilds_catalog_json(tmp_path: Path) -> None:
    """catalog.json is rebuilt to match .md frontmatter on disk."""
    kb = _init_kb(tmp_path)

    # Manually corrupt catalog.json (empty)
    (kb / "catalog.json").write_text("[]")

    # Write a paper with frontmatter
    _write_md(
        kb,
        "papers/hydrology/rainfall-2024.md",
        {
            "id": "rainfall-2024",
            "type": "paper",
            "title": "Rainfall Estimation",
            "topic": "hydrology",
            "added": "2024-01-10",
        },
    )

    result = runner.invoke(app, ["--kb", str(kb), "reindex"])
    assert result.exit_code == 0, result.output
    assert "1" in result.output  # 1 entry reported

    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 1
    assert catalog[0]["id"] == "rainfall-2024"
    assert catalog[0]["type"] == "paper"


# ---------------------------------------------------------------------------
# Test 2: catalog.md is regenerated
# ---------------------------------------------------------------------------


def test_reindex_regenerates_catalog_md(tmp_path: Path) -> None:
    """catalog.md is rewritten to reflect current entries after reindex."""
    kb = _init_kb(tmp_path)

    _write_md(
        kb,
        "papers/remote-sensing/ndvi-2023.md",
        {
            "id": "ndvi-2023",
            "type": "paper",
            "title": "NDVI Analysis",
            "topic": "remote-sensing",
            "added": "2023-06-01",
        },
    )

    result = runner.invoke(app, ["--kb", str(kb), "reindex"])
    assert result.exit_code == 0, result.output

    catalog_md = (kb / "catalog.md").read_text()
    assert "NDVI Analysis" in catalog_md
    assert "Papers" in catalog_md


# ---------------------------------------------------------------------------
# Test 3: works with mix of papers, packages, and codebases
# ---------------------------------------------------------------------------


def test_reindex_mixed_entry_types(tmp_path: Path) -> None:
    """Reindex handles papers, packages, and codebases together."""
    kb = _init_kb(tmp_path)

    _write_md(
        kb,
        "papers/hydrology/streamflow.md",
        {
            "id": "p1",
            "type": "paper",
            "title": "Streamflow Study",
            "topic": "hydrology",
        },
    )
    _write_md(
        kb,
        "packages/hydrotools/index.md",
        {"id": "pkg1", "type": "package", "title": "HydroTools"},
    )
    _write_md(
        kb,
        "codebases/swatplus/index.md",
        {"id": "cb1", "type": "codebase", "title": "SWAT+ Model"},
    )

    result = runner.invoke(app, ["--kb", str(kb), "reindex"])
    assert result.exit_code == 0, result.output
    assert "3" in result.output

    catalog = json.loads((kb / "catalog.json").read_text())
    types = {e["type"] for e in catalog}
    assert types == {"paper", "package", "codebase"}

    catalog_md = (kb / "catalog.md").read_text()
    assert "Papers" in catalog_md
    assert "Packages" in catalog_md
    assert "Codebases" in catalog_md


# ---------------------------------------------------------------------------
# Test 4: skips files without frontmatter `type` field
# ---------------------------------------------------------------------------


def test_reindex_skips_files_without_type(tmp_path: Path) -> None:
    """Files missing the `type` frontmatter field are excluded from catalog."""
    kb = _init_kb(tmp_path)

    # Valid entry
    _write_md(
        kb,
        "papers/hydrology/valid.md",
        {
            "id": "valid-1",
            "type": "paper",
            "title": "Valid Paper",
            "topic": "hydrology",
        },
    )

    # File with frontmatter but no `type`
    no_type = kb / "papers" / "hydrology" / "no-type.md"
    no_type.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("# No type field")
    post.metadata = {"id": "no-type", "title": "Missing Type"}
    no_type.write_text(frontmatter.dumps(post))

    # Plain markdown with no frontmatter at all
    plain = kb / "papers" / "hydrology" / "plain.md"
    plain.write_text("# Just a plain markdown file\n\nNo frontmatter.")

    result = runner.invoke(app, ["--kb", str(kb), "reindex"])
    assert result.exit_code == 0, result.output

    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 1
    assert catalog[0]["id"] == "valid-1"


# ---------------------------------------------------------------------------
# Test 5: skips .hydrofound/ directory
# ---------------------------------------------------------------------------


def test_reindex_skips_hydrofound_directory(tmp_path: Path) -> None:
    """Files inside .hydrofound/ are never indexed."""
    kb = _init_kb(tmp_path)

    # Write a valid paper
    _write_md(
        kb,
        "papers/hydrology/real.md",
        {"id": "real-1", "type": "paper", "title": "Real Paper", "topic": "hydrology"},
    )

    # Manually plant a .md inside .hydrofound/ that looks like an entry
    internal_md = kb / ".hydrofound" / "internal.md"
    internal_post = frontmatter.Post("# Internal")
    internal_post.metadata = {"id": "internal", "type": "paper", "title": "Internal"}
    internal_md.write_text(frontmatter.dumps(internal_post))

    result = runner.invoke(app, ["--kb", str(kb), "reindex"])
    assert result.exit_code == 0, result.output

    catalog = json.loads((kb / "catalog.json").read_text())
    ids = [e["id"] for e in catalog]
    assert "internal" not in ids
    assert "real-1" in ids


# ---------------------------------------------------------------------------
# Test 6: error when --kb missing or not initialized
# ---------------------------------------------------------------------------


def test_reindex_requires_initialized_kb(tmp_path: Path) -> None:
    """Reindex exits with error when KB is not initialized."""
    # No --kb at all
    result = runner.invoke(app, ["reindex"])
    assert result.exit_code != 0

    # --kb points to a non-initialized directory
    not_kb = tmp_path / "not_a_kb"
    not_kb.mkdir()
    result = runner.invoke(app, ["--kb", str(not_kb), "reindex"])
    assert result.exit_code != 0
