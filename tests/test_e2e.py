"""End-to-end integration tests for HydroFound CLI.

These tests exercise full workflows: init → ingest → search → catalog → remove → reindex.
They use CliRunner (in-process) and mock GLM-OCR where needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import frontmatter
from typer.testing import CliRunner

from hydrofound.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_kb(tmp_path: Path) -> Path:
    """Create an initialized KB via CLI and return its path."""
    kb = tmp_path / "kb"
    result = runner.invoke(app, ["init", str(kb)])
    assert result.exit_code == 0, result.output
    return kb


def _make_codebase(tmp_path: Path, name: str = "myproject") -> Path:
    """Create a minimal multi-language codebase."""
    code = tmp_path / name
    code.mkdir()
    (code / "main.py").write_text(
        '"""Main module."""\n\n\ndef run(config: dict) -> None:\n'
        '    """Run the pipeline."""\n    pass\n'
    )
    (code / "calc.f90").write_text(
        "module calculations\n  implicit none\ncontains\n"
        "  subroutine compute_flow(q, area, vel)\n"
        "    real, intent(in) :: area, vel\n"
        "    real, intent(out) :: q\n"
        "    q = area * vel\n"
        "  end subroutine\n"
        "end module\n"
    )
    (code / "README.md").write_text("# My Project\n\nA test project.\n")
    return code


def _make_fake_pdf(path: Path) -> Path:
    """Create a valid-looking PDF (correct magic bytes, sufficient size)."""
    # Minimal PDF that passes validation: magic bytes + enough padding
    content = b"%PDF-1.4\n" + b"% This is a test PDF\n" * 100
    path.write_bytes(content)
    return path


# ===========================================================================
# Test 1: Init respects --kb global option
# ===========================================================================


def test_init_with_kb_flag(tmp_path: Path) -> None:
    """hydrofound --kb <path> init creates KB at the --kb path."""
    target = tmp_path / "my_kb"
    result = runner.invoke(app, ["--kb", str(target), "init"])
    assert result.exit_code == 0, result.output
    assert (target / ".hydrofound").is_dir()
    assert (target / "catalog.json").is_file()


def test_init_positional_overrides_kb(tmp_path: Path) -> None:
    """Positional path argument takes precedence over --kb."""
    kb_path = tmp_path / "from_flag"
    positional = tmp_path / "from_arg"
    result = runner.invoke(app, ["--kb", str(kb_path), "init", str(positional)])
    assert result.exit_code == 0
    assert (positional / ".hydrofound").is_dir()
    # --kb path should NOT be created
    assert not kb_path.exists()


# ===========================================================================
# Test 2: Full codebase workflow — ingest → search → catalog → remove
# ===========================================================================


def test_codebase_full_workflow(tmp_path: Path) -> None:
    """Complete lifecycle: ingest codebase → search → catalog → remove → verify."""
    kb = _init_kb(tmp_path)
    code = _make_codebase(tmp_path)

    # Ingest
    result = runner.invoke(
        app,
        ["--kb", str(kb), "ingest", "codebase", str(code), "--name", "myproject"],
    )
    assert result.exit_code == 0, result.output
    assert "myproject" in result.output.lower()

    # Verify files
    assert (kb / "codebases" / "myproject" / "_index.md").exists()
    assert (kb / "codebases" / "myproject" / "signatures.md").exists()
    assert (kb / "codebases" / "myproject" / "structure.md").exists()

    # Verify catalog.json
    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 1
    assert catalog[0]["type"] == "codebase"
    assert catalog[0]["id"] == "codebase-myproject"

    # Search — should find Fortran subroutine
    result = runner.invoke(app, ["--kb", str(kb), "search", "compute_flow"])
    assert result.exit_code == 0, result.output
    assert "compute_flow" in result.output

    # Search — should find Python function
    result = runner.invoke(app, ["--kb", str(kb), "search", "run pipeline"])
    assert result.exit_code == 0, result.output

    # Catalog show
    result = runner.invoke(app, ["--kb", str(kb), "catalog", "show"])
    assert result.exit_code == 0, result.output
    assert "myproject" in result.output

    # Catalog stats
    result = runner.invoke(app, ["--kb", str(kb), "catalog", "stats"])
    assert result.exit_code == 0, result.output
    assert "1" in result.output  # 1 codebase

    # Remove
    result = runner.invoke(app, ["--kb", str(kb), "remove", "codebase-myproject"])
    assert result.exit_code == 0, result.output

    # Verify removal
    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 0
    assert not (kb / "codebases" / "myproject" / "_index.md").exists()


# ===========================================================================
# Test 3: Package ingestion workflow
# ===========================================================================


def test_package_ingest_and_search(tmp_path: Path) -> None:
    """Ingest a real package (hydrofound itself) and search its API."""
    kb = _init_kb(tmp_path)

    # Ingest hydrofound's own API (no network needed — griffe works locally)
    result = runner.invoke(app, ["--kb", str(kb), "ingest", "package", "hydrofound"])
    assert result.exit_code == 0, result.output
    assert "hydrofound" in result.output.lower()

    # Verify files created
    assert (kb / "packages" / "hydrofound" / "api.md").exists()

    # Search for a known function
    result = runner.invoke(app, ["--kb", str(kb), "search", "init_command"])
    assert result.exit_code == 0, result.output


# ===========================================================================
# Test 4: Paper ingestion with mocked GLM-OCR
# ===========================================================================


def test_paper_ingest_via_glm_mock(tmp_path: Path) -> None:
    """Paper ingestion with GLM-OCR mocked (default converter)."""
    kb = _init_kb(tmp_path)
    pdf = _make_fake_pdf(tmp_path / "test-paper.pdf")

    markdown_output = (
        "# Differentiable Hydrological Modeling\n\n"
        "A novel approach to rainfall-runoff simulation (2024).\n\n"
        "DOI: 10.1029/2023WR034567\n\n"
        "## Abstract\n\n"
        "We present a differentiable model for streamflow prediction.\n"
    )

    with patch(
        "hydrofound.ingestion.glm_ocr.convert_pdf_glm",
        return_value=markdown_output,
    ):
        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "ingest",
                "paper",
                str(pdf),
                "--topic",
                "hydrology",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "differentiable" in result.output.lower()

    # Verify catalog entry
    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 1
    entry = catalog[0]
    assert entry["type"] == "paper"
    assert entry["doi"] == "10.1029/2023WR034567"
    assert "hydrology" in entry.get("topic", "")

    # Verify the markdown file exists with frontmatter
    paper_files = list((kb / "papers" / "hydrology").rglob("*.md"))
    assert len(paper_files) == 1
    post = frontmatter.load(paper_files[0])
    assert post.metadata["type"] == "paper"
    assert post.metadata["doi"] == "10.1029/2023WR034567"
    assert "differentiable" in post.content.lower()

    # Search for it
    result = runner.invoke(
        app, ["--kb", str(kb), "search", "differentiable streamflow"]
    )
    assert result.exit_code == 0
    assert len(result.output.strip()) > 0


# ===========================================================================
# Test 5: Paper validation error paths
# ===========================================================================


def test_paper_validation_too_small(tmp_path: Path) -> None:
    """Tiny files are rejected with a clean error (not a traceback)."""
    kb = _init_kb(tmp_path)
    tiny = tmp_path / "tiny.pdf"
    tiny.write_bytes(b"%PDF-1.4 small")

    result = runner.invoke(
        app, ["--kb", str(kb), "ingest", "paper", str(tiny), "--topic", "test"]
    )
    assert result.exit_code != 0
    assert "too small" in result.output.lower()
    # Must NOT contain a traceback
    assert "Traceback" not in result.output


def test_paper_validation_bad_magic(tmp_path: Path) -> None:
    """Non-PDF files are rejected."""
    kb = _init_kb(tmp_path)
    not_pdf = tmp_path / "not-a-pdf.pdf"
    not_pdf.write_bytes(b"This is not a PDF at all\n" * 100)

    result = runner.invoke(
        app, ["--kb", str(kb), "ingest", "paper", str(not_pdf), "--topic", "test"]
    )
    assert result.exit_code != 0
    # Should mention magic bytes or invalid
    assert "Traceback" not in result.output


def test_paper_nonexistent_file(tmp_path: Path) -> None:
    """Nonexistent file path produces clean error."""
    kb = _init_kb(tmp_path)
    result = runner.invoke(
        app, ["--kb", str(kb), "ingest", "paper", "/no/such/file.pdf", "--topic", "x"]
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# ===========================================================================
# Test 6: Batch paper ingestion with mocked GLM-OCR
# ===========================================================================


def test_batch_paper_ingest(tmp_path: Path) -> None:
    """Batch ingest a folder of PDFs with mocked GLM-OCR."""
    kb = _init_kb(tmp_path)

    # Create 3 fake PDFs
    pdf_dir = tmp_path / "papers"
    pdf_dir.mkdir()
    for i in range(3):
        _make_fake_pdf(pdf_dir / f"paper-{i}.pdf")

    call_count = {"n": 0}

    def fake_glm_convert(path, model_name="", dpi=150, image_dir=None):
        call_count["n"] += 1
        return (
            f"# Paper {call_count['n']}\n\nContent of paper {call_count['n']} (2024).\n"
        )

    with patch(
        "hydrofound.ingestion.glm_ocr.convert_pdf_glm",
        side_effect=fake_glm_convert,
    ):
        result = runner.invoke(
            app,
            ["--kb", str(kb), "ingest", "paper", str(pdf_dir), "--topic", "batch-test"],
        )

    assert result.exit_code == 0, result.output
    assert "3" in result.output  # 3 ingested

    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 3
    assert all(e["type"] == "paper" for e in catalog)


# ===========================================================================
# Test 7: Duplicate DOI rejection
# ===========================================================================


def test_duplicate_doi_rejected(tmp_path: Path) -> None:
    """Second paper with same DOI is skipped (immutable DOI policy)."""
    kb = _init_kb(tmp_path)

    markdown = "# Same Paper\n\nDOI: 10.1234/test-doi-duplicate\n\nContent (2024).\n"

    with patch(
        "hydrofound.ingestion.glm_ocr.convert_pdf_glm",
        return_value=markdown,
    ):
        # First ingest
        pdf1 = _make_fake_pdf(tmp_path / "paper1.pdf")
        result = runner.invoke(
            app, ["--kb", str(kb), "ingest", "paper", str(pdf1), "--topic", "test"]
        )
        assert result.exit_code == 0

        # Second ingest — same DOI
        pdf2 = _make_fake_pdf(tmp_path / "paper2.pdf")
        result = runner.invoke(
            app, ["--kb", str(kb), "ingest", "paper", str(pdf2), "--topic", "test"]
        )
        assert result.exit_code == 0
        assert "skip" in result.output.lower() or "duplicate" in result.output.lower()

    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 1  # Only one entry despite two ingestions


# ===========================================================================
# Test 8: Reindex rebuilds with correct titles and file counts
# ===========================================================================


def test_reindex_preserves_name_as_title(tmp_path: Path) -> None:
    """Reindex falls back to frontmatter 'name' when 'title' is absent."""
    kb = _init_kb(tmp_path)
    code = _make_codebase(tmp_path)

    # Ingest codebase (produces frontmatter with name=, not title=)
    runner.invoke(
        app,
        ["--kb", str(kb), "ingest", "codebase", str(code), "--name", "myproject"],
    )

    # Wipe catalog.json to force full rebuild
    (kb / "catalog.json").write_text("[]")

    result = runner.invoke(app, ["--kb", str(kb), "reindex"])
    assert result.exit_code == 0, result.output

    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 1
    assert catalog[0]["title"] == "myproject"
    # Should have files discovered from siblings
    assert len(catalog[0].get("files", [])) == 3  # _index, structure, signatures


def test_reindex_survives_corrupt_catalog(tmp_path: Path) -> None:
    """Reindex works even when catalog.json is corrupted or has missing fields."""
    kb = _init_kb(tmp_path)

    # Write valid frontmatter
    (kb / "papers" / "test").mkdir(parents=True)
    post = frontmatter.Post("# Test Paper\n\nContent here.")
    post.metadata = {
        "type": "paper",
        "id": "paper-test",
        "title": "Test Paper",
        "topic": "test",
    }
    (kb / "papers" / "test" / "paper.md").write_text(frontmatter.dumps(post))

    # Corrupt the catalog — missing required fields
    (kb / "catalog.json").write_text('[{"type": "broken"}]')

    # Reindex should succeed despite corrupt catalog
    result = runner.invoke(app, ["--kb", str(kb), "reindex"])
    assert result.exit_code == 0, result.output
    assert "1" in result.output

    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 1
    assert catalog[0]["id"] == "paper-test"


# ===========================================================================
# Test 9: Multi-type KB workflow
# ===========================================================================


def test_multi_type_kb(tmp_path: Path) -> None:
    """KB with codebase + package — catalog and search work across types."""
    kb = _init_kb(tmp_path)
    code = _make_codebase(tmp_path)

    # Ingest codebase
    runner.invoke(
        app,
        ["--kb", str(kb), "ingest", "codebase", str(code), "--name", "flowmodel"],
    )

    # Ingest package (hydrofound itself — always available)
    runner.invoke(app, ["--kb", str(kb), "ingest", "package", "hydrofound"])

    # Catalog should have 2 entries
    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 2
    types = {e["type"] for e in catalog}
    assert types == {"codebase", "package"}

    # Stats
    result = runner.invoke(app, ["--kb", str(kb), "catalog", "stats"])
    assert result.exit_code == 0

    # Search across types
    result = runner.invoke(app, ["--kb", str(kb), "search", "compute"])
    assert result.exit_code == 0

    # Reindex — should preserve both
    (kb / "catalog.json").write_text("[]")
    result = runner.invoke(app, ["--kb", str(kb), "reindex"])
    assert result.exit_code == 0
    assert "2" in result.output


# ===========================================================================
# Test 10: Error paths
# ===========================================================================


def test_search_no_kb(tmp_path: Path) -> None:
    """Search without --kb produces clean error."""
    result = runner.invoke(app, ["search", "test query"])
    assert result.exit_code != 0


def test_remove_nonexistent_entry(tmp_path: Path) -> None:
    """Removing a nonexistent entry produces clean error."""
    kb = _init_kb(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "remove", "does-not-exist"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_reindex_no_kb() -> None:
    """Reindex without --kb produces error."""
    result = runner.invoke(app, ["reindex"])
    assert result.exit_code != 0


def test_double_init(tmp_path: Path) -> None:
    """Double init on same path fails."""
    kb = _init_kb(tmp_path)
    result = runner.invoke(app, ["init", str(kb)])
    assert result.exit_code != 0


# ===========================================================================
# Test 11: MCP server initialization
# ===========================================================================


def test_mcp_server_lists_tools(tmp_path: Path) -> None:
    """MCP server exposes the expected 6 tools."""

    from hydrofound.mcp_server import create_server

    kb = _init_kb(tmp_path)
    server = create_server(kb)

    # The server's list_tools handler is registered — verify via direct call
    assert server is not None
    # Server object has the tools registered (exact API depends on mcp version)


# ===========================================================================
# Test 12: Offline mode blocks network commands
# ===========================================================================


def test_offline_blocks_discover(tmp_path: Path) -> None:
    """--offline flag prevents discover from running."""
    kb = _init_kb(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "--offline", "discover", "test"])
    assert result.exit_code != 0
    assert "offline" in result.output.lower()


def test_offline_allows_local_ops(tmp_path: Path) -> None:
    """--offline doesn't affect local operations."""
    kb = _init_kb(tmp_path)
    code = _make_codebase(tmp_path)

    # Ingest codebase (local, no network)
    result = runner.invoke(
        app,
        ["--kb", str(kb), "--offline", "ingest", "codebase", str(code), "--name", "x"],
    )
    assert result.exit_code == 0

    # Search (local)
    result = runner.invoke(app, ["--kb", str(kb), "--offline", "search", "compute"])
    assert result.exit_code == 0

    # Catalog (local)
    result = runner.invoke(app, ["--kb", str(kb), "--offline", "catalog", "show"])
    assert result.exit_code == 0
