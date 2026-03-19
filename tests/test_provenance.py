"""Tests for code-to-paper provenance annotations."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from papermind.cli.main import app
from papermind.provenance import (
    CodeRef,
    extract_provenance,
    format_provenance,
    scan_codebase_provenance,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Annotation parsing — single file
# ---------------------------------------------------------------------------


class TestExtractProvenance:
    """Test # REF: annotation extraction from source files."""

    def test_python_doi_annotation(self, tmp_path: Path) -> None:
        """Parse a Python # REF: with DOI."""
        src = tmp_path / "model.py"
        src.write_text(
            "def calc_runoff():\n"
            "    # REF: doi:10.1016/j.jhydrol.2012.03.001 eq.4.2\n"
            "    return precip * cn\n"
        )
        refs = extract_provenance(src)
        assert len(refs) == 1
        assert refs[0].identifier == "10.1016/j.jhydrol.2012.03.001"
        assert refs[0].identifier_type == "doi"
        assert refs[0].location == "eq.4.2"
        assert refs[0].line == 2

    def test_python_paper_id_annotation(self, tmp_path: Path) -> None:
        """Parse a paper-ID reference."""
        src = tmp_path / "model.py"
        src.write_text("# REF: paper-green-ampt-1911 §methods\nx = 1\n")
        refs = extract_provenance(src)
        assert len(refs) == 1
        assert refs[0].identifier == "paper-green-ampt-1911"
        assert refs[0].identifier_type == "paper_id"
        assert refs[0].location == "§methods"

    def test_fortran_annotation(self, tmp_path: Path) -> None:
        """Parse a Fortran ! REF: annotation."""
        src = tmp_path / "model.f90"
        src.write_text(
            "subroutine percolation(soil)\n"
            "  ! REF: doi:10.5194/hess-25-2019-2021\n"
            "  real :: soil\n"
            "end subroutine\n"
        )
        refs = extract_provenance(src)
        assert len(refs) == 1
        assert refs[0].identifier == "10.5194/hess-25-2019-2021"

    def test_c_annotation(self, tmp_path: Path) -> None:
        """Parse a C // REF: annotation."""
        src = tmp_path / "model.c"
        src.write_text("// REF: doi:10.1029/2023WR035123 eq.7\nint x = 0;\n")
        refs = extract_provenance(src)
        assert len(refs) == 1
        assert refs[0].identifier == "10.1029/2023WR035123"

    def test_inline_annotation(self, tmp_path: Path) -> None:
        """Parse inline annotation after code."""
        src = tmp_path / "model.py"
        src.write_text("x = compute_baseflow(params)  # REF: doi:10.1234/bf2020 eq.3\n")
        refs = extract_provenance(src)
        assert len(refs) == 1
        assert refs[0].identifier == "10.1234/bf2020"
        assert refs[0].location == "eq.3"

    def test_doi_without_prefix(self, tmp_path: Path) -> None:
        """DOI without explicit doi: prefix."""
        src = tmp_path / "model.py"
        src.write_text("# REF: 10.1016/j.jhydrol.2021.126601\n")
        refs = extract_provenance(src)
        assert len(refs) == 1
        assert refs[0].identifier == "10.1016/j.jhydrol.2021.126601"

    def test_no_annotations(self, tmp_path: Path) -> None:
        """File without annotations returns empty list."""
        src = tmp_path / "model.py"
        src.write_text("# This is a regular comment\ndef foo(): pass\n")
        refs = extract_provenance(src)
        assert refs == []

    def test_multiple_annotations(self, tmp_path: Path) -> None:
        """Multiple annotations in one file."""
        src = tmp_path / "model.py"
        src.write_text(
            "# REF: doi:10.1234/paper1 eq.1\n"
            "x = 1\n"
            "# REF: doi:10.5678/paper2 eq.2\n"
            "y = 2\n"
            "z = x + y  # REF: paper-summary-2020\n"
        )
        refs = extract_provenance(src)
        assert len(refs) == 3

    def test_relative_path(self, tmp_path: Path) -> None:
        """File path is relative to root when root is provided."""
        sub = tmp_path / "src" / "model"
        sub.mkdir(parents=True)
        src = sub / "water_balance.py"
        src.write_text("# REF: doi:10.1234/test\n")

        refs = extract_provenance(src, root=tmp_path)
        assert refs[0].file == "src/model/water_balance.py"

    def test_annotation_no_location(self, tmp_path: Path) -> None:
        """Annotation without location specifier."""
        src = tmp_path / "model.py"
        src.write_text("# REF: doi:10.1234/general\n")
        refs = extract_provenance(src)
        assert refs[0].location == ""


# ---------------------------------------------------------------------------
# Codebase scan
# ---------------------------------------------------------------------------


class TestScanCodebaseProvenance:
    """Test codebase-level provenance scanning."""

    def test_scan_finds_refs(self, tmp_path: Path) -> None:
        """Scan finds annotations across multiple files."""
        (tmp_path / "a.py").write_text("# REF: doi:10.1234/paper-a\ndef foo(): pass\n")
        (tmp_path / "b.py").write_text("# No refs here\ndef bar(): pass\n")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.f90").write_text("! REF: doi:10.5678/paper-c eq.1\n")

        summary = scan_codebase_provenance(tmp_path)
        assert summary.files_with_refs == 2
        assert summary.total_refs == 2
        assert summary.unique_papers == 2

    def test_scan_empty_codebase(self, tmp_path: Path) -> None:
        """Scan of empty directory returns zero counts."""
        summary = scan_codebase_provenance(tmp_path)
        assert summary.total_refs == 0
        assert summary.files_scanned == 0

    def test_scan_respects_gitignore(self, tmp_path: Path) -> None:
        """Files matching .gitignore are skipped."""
        (tmp_path / ".gitignore").write_text("build/\n*.pyc\n")
        build = tmp_path / "build"
        build.mkdir()
        (build / "generated.py").write_text("# REF: doi:10.1234/should-skip\n")
        (tmp_path / "real.py").write_text("# REF: doi:10.1234/keep\n")

        summary = scan_codebase_provenance(tmp_path)
        assert summary.total_refs == 1
        assert "real.py" in summary.refs_by_file


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


class TestFormatProvenance:
    """Test output formatting."""

    def test_format_empty(self) -> None:
        assert "No # REF:" in format_provenance([])

    def test_format_with_refs(self) -> None:
        refs = [
            CodeRef(
                file="model.py",
                line=10,
                identifier="10.1234/test",
                identifier_type="doi",
                location="eq.4",
                raw="# REF: doi:10.1234/test eq.4",
            )
        ]
        text = format_provenance(refs)
        assert "L10" in text
        assert "10.1234/test" in text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestProvenanceCLI:
    """Test CLI commands."""

    def test_provenance_show(self, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text("# REF: doi:10.1234/cli-test eq.1\ndef f(): pass\n")

        result = runner.invoke(app, ["provenance", "show", str(src)])
        assert result.exit_code == 0
        assert "10.1234/cli-test" in result.output

    def test_provenance_scan(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("# REF: doi:10.1234/scan\n")

        result = runner.invoke(app, ["provenance", "scan", str(tmp_path)])
        assert result.exit_code == 0
        assert "Provenance Scan" in result.output

    def test_provenance_show_no_refs(self, tmp_path: Path) -> None:
        src = tmp_path / "clean.py"
        src.write_text("def clean(): pass\n")

        result = runner.invoke(app, ["provenance", "show", str(src)])
        assert result.exit_code == 0
        assert "No # REF:" in result.output
