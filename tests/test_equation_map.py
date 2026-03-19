"""Tests for equation-to-code mapping."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from papermind.cli.main import app
from papermind.equation_map import (
    extract_code_variables,
    extract_latex_symbols,
    format_equation_map,
    map_equation_to_code,
    match_symbols_to_variables,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# LaTeX symbol extraction
# ---------------------------------------------------------------------------


class TestExtractLatexSymbols:
    """Test symbol extraction from LaTeX equations."""

    def test_simple_uppercase_vars(self) -> None:
        symbols = extract_latex_symbols("Q = C \\cdot I \\cdot A")
        assert "Q" in symbols
        assert "C" in symbols
        assert "A" in symbols
        assert "I" in symbols

    def test_greek_letters(self) -> None:
        symbols = extract_latex_symbols("\\alpha + \\beta = \\gamma")
        assert "alpha" in symbols
        assert "beta" in symbols
        assert "gamma" in symbols

    def test_subscripted_symbols(self) -> None:
        symbols = extract_latex_symbols("K_{sat} \\cdot S_{w}")
        assert "K_sat" in symbols or "K_{sat}" in symbols
        assert "S_w" in symbols or "S_{w}" in symbols

    def test_simple_subscript(self) -> None:
        symbols = extract_latex_symbols("Q_s + Q_b")
        assert "Q_s" in symbols
        assert "Q_b" in symbols

    def test_operators_filtered(self) -> None:
        symbols = extract_latex_symbols("\\frac{Q}{A} = \\sqrt{\\sum x}")
        assert "frac" not in symbols
        assert "sqrt" not in symbols
        assert "sum" not in symbols

    def test_empty_equation(self) -> None:
        assert extract_latex_symbols("") == []

    def test_complex_equation(self) -> None:
        """Real SWAT+ percolation equation."""
        latex = "w_{perc} = SW \\cdot (1 - \\exp(-\\Delta t / TT_{perc}))"
        symbols = extract_latex_symbols(latex)
        assert "w_perc" in symbols or "w_{perc}" in symbols


# ---------------------------------------------------------------------------
# Code variable extraction
# ---------------------------------------------------------------------------


class TestExtractCodeVariables:
    """Test variable extraction from source files."""

    def test_python_function_args(self, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text(
            "def calc_runoff(precip, cn, area):\n"
            "    runoff = precip * cn\n"
            "    return runoff * area\n"
        )
        variables = extract_code_variables(src, "calc_runoff")
        assert "precip" in variables
        assert "cn" in variables
        assert "area" in variables
        assert "runoff" in variables

    def test_python_all_variables(self, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text("x = 1\ny = 2\nz = x + y\n")
        variables = extract_code_variables(src)
        assert "x" in variables
        assert "y" in variables
        assert "z" in variables

    def test_fortran_variables(self, tmp_path: Path) -> None:
        src = tmp_path / "solver.f90"
        src.write_text(
            "subroutine calc(discharge, area)\n"
            "  real :: discharge, area\n"
            "  real :: velocity\n"
            "  velocity = discharge / area\n"
            "end subroutine\n"
        )
        variables = extract_code_variables(src)
        assert "discharge" in variables
        assert "area" in variables


# ---------------------------------------------------------------------------
# Symbol matching
# ---------------------------------------------------------------------------


class TestMatchSymbolsToVariables:
    """Test the matching engine."""

    def test_exact_match(self) -> None:
        mappings, unmatched_sym, unmatched_var = match_symbols_to_variables(
            ["Q", "A"], ["Q", "A", "extra"]
        )
        assert len(mappings) == 2
        assert all(m.method == "exact" for m in mappings)

    def test_normalized_match(self) -> None:
        """K_sat should match k_sat or ksat."""
        mappings, _, _ = match_symbols_to_variables(["K_sat"], ["k_sat"])
        assert len(mappings) == 1
        assert mappings[0].confidence >= 0.9

    def test_greek_to_code(self) -> None:
        """\\alpha should match 'alpha' variable."""
        mappings, _, _ = match_symbols_to_variables(["alpha"], ["alpha", "beta"])
        assert len(mappings) >= 1
        assert mappings[0].variable == "alpha"

    def test_unmatched_reported(self) -> None:
        _, unmatched_sym, unmatched_var = match_symbols_to_variables(
            ["Q", "mystery"], ["discharge", "extra"]
        )
        assert "mystery" in unmatched_sym
        assert "extra" in unmatched_var or "discharge" in unmatched_var

    def test_empty_inputs(self) -> None:
        mappings, unmatched_sym, unmatched_var = match_symbols_to_variables([], [])
        assert mappings == []
        assert unmatched_sym == []
        assert unmatched_var == []


# ---------------------------------------------------------------------------
# High-level mapping
# ---------------------------------------------------------------------------


class TestMapEquationToCode:
    """Test end-to-end equation-to-code mapping."""

    def test_map_simple_equation(self, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text("def calc(Q, A, velocity):\n    return Q / A\n")
        result = map_equation_to_code("Q = V \\cdot A", src, "calc")
        assert len(result.mappings) >= 2  # Q→Q, A→A at least

    def test_map_with_greek(self, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text("def bf(alpha, beta):\n    return alpha * beta\n")
        result = map_equation_to_code("\\alpha \\cdot \\beta", src, "bf")
        assert any(
            m.symbol == "alpha" and m.variable == "alpha" for m in result.mappings
        )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


class TestFormatEquationMap:
    """Test output formatting."""

    def test_format_with_mappings(self, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text("def f(Q, A):\n    return Q / A\n")
        result = map_equation_to_code("Q = V \\cdot A", src, "f")
        text = format_equation_map(result)
        assert "Mappings" in text
        assert "Symbol" in text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestEquationMapCLI:
    """Test CLI command."""

    def test_equation_map_basic(self, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text("def calc(Q, A):\n    V = Q / A\n    return V\n")

        result = runner.invoke(
            app,
            ["equation-map", str(src), "-e", "Q = V \\cdot A"],
        )
        assert result.exit_code == 0

    def test_equation_map_with_function(self, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text(
            "def other(): pass\n\ndef calc(alpha, beta):\n    return alpha * beta\n"
        )

        result = runner.invoke(
            app,
            [
                "equation-map",
                f"{src}::calc",
                "-e",
                "\\alpha \\cdot \\beta",
            ],
        )
        assert result.exit_code == 0

    def test_equation_map_no_equation(self, tmp_path: Path) -> None:
        src = tmp_path / "model.py"
        src.write_text("x = 1\n")

        result = runner.invoke(app, ["equation-map", str(src)])
        assert result.exit_code == 1
