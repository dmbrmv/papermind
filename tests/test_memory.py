"""Tests for agent memory integration (kb: references)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from papermind.cli.main import app
from papermind.memory import (
    extract_kb_refs,
    extract_kb_refs_from_file,
    resolve_refs,
    validate_refs_in_file,
)

runner = CliRunner()


def _make_kb(tmp_path: Path) -> Path:
    """Create a minimal KB with a paper."""
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()

    from papermind.catalog.index import CatalogEntry, CatalogIndex

    catalog = CatalogIndex(kb)
    catalog.add(
        CatalogEntry(
            id="paper-test-2020",
            type="paper",
            path="papers/hydrology/test/paper.md",
            title="Test Paper on Hydrology",
            doi="10.1234/test2020",
            topic="hydrology",
        )
    )
    return kb


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestExtractKBRefs:
    """Test kb: reference extraction from text."""

    def test_paper_id_ref(self) -> None:
        text = "See kb:paper-green-ampt-1911 for details."
        refs = extract_kb_refs(text)
        assert len(refs) == 1
        assert refs[0].identifier == "paper-green-ampt-1911"
        assert refs[0].identifier_type == "paper_id"

    def test_doi_ref(self) -> None:
        text = "Based on kb:doi:10.1016/j.jhydrol.2012.03.001."
        refs = extract_kb_refs(text)
        assert len(refs) == 1
        assert refs[0].identifier == "10.1016/j.jhydrol.2012.03.001"
        assert refs[0].identifier_type == "doi"

    def test_multiple_refs(self) -> None:
        text = (
            "Uses kb:paper-scs-cn-1986 and kb:paper-green-ampt-1911.\n"
            "Also see kb:doi:10.5555/other.\n"
        )
        refs = extract_kb_refs(text)
        assert len(refs) == 3

    def test_no_refs(self) -> None:
        text = "No references here. Just regular text."
        refs = extract_kb_refs(text)
        assert refs == []

    def test_line_numbers(self) -> None:
        text = "Line 1\nLine 2 has kb:paper-test-2020 ref.\nLine 3\n"
        refs = extract_kb_refs(text)
        assert refs[0].line == 2

    def test_from_file(self, tmp_path: Path) -> None:
        md = tmp_path / "notes.md"
        md.write_text("# Notes\n\nSee kb:paper-test-2020 for context.\n")
        refs = extract_kb_refs_from_file(md)
        assert len(refs) == 1


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


class TestResolveRefs:
    """Test resolving refs against KB."""

    def test_found_by_id(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        refs = extract_kb_refs("See kb:paper-test-2020.")
        resolved = resolve_refs(refs, kb)
        assert len(resolved) == 1
        assert resolved[0].found is True
        assert resolved[0].title == "Test Paper on Hydrology"

    def test_found_by_doi(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        refs = extract_kb_refs("See kb:doi:10.1234/test2020.")
        resolved = resolve_refs(refs, kb)
        assert len(resolved) == 1
        assert resolved[0].found is True

    def test_not_found(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        refs = extract_kb_refs("See kb:paper-nonexistent.")
        resolved = resolve_refs(refs, kb)
        assert len(resolved) == 1
        assert resolved[0].found is False


class TestValidateRefs:
    """Test file-level validation."""

    def test_all_valid(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        md = tmp_path / "notes.md"
        md.write_text("Uses kb:paper-test-2020.\n")

        valid, broken = validate_refs_in_file(md, kb)
        assert len(valid) == 1
        assert len(broken) == 0

    def test_broken_ref(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        md = tmp_path / "notes.md"
        md.write_text("Uses kb:paper-nonexistent.\n")

        valid, broken = validate_refs_in_file(md, kb)
        assert len(valid) == 0
        assert len(broken) == 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestMemoryCLI:
    """Test CLI commands."""

    def test_resolve_cmd(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        md = tmp_path / "notes.md"
        md.write_text("See kb:paper-test-2020 for details.\n")

        result = runner.invoke(app, ["--kb", str(kb), "resolve", str(md)])
        assert result.exit_code == 0
        assert "Test Paper" in result.output

    def test_validate_refs_cmd_valid(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        md = tmp_path / "notes.md"
        md.write_text("Uses kb:paper-test-2020.\n")

        result = runner.invoke(app, ["--kb", str(kb), "validate-refs", str(md)])
        assert result.exit_code == 0

    def test_validate_refs_cmd_broken(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        md = tmp_path / "notes.md"
        md.write_text("Uses kb:paper-broken.\n")

        result = runner.invoke(app, ["--kb", str(kb), "validate-refs", str(md)])
        assert result.exit_code == 1
