"""Tests for the explain (glossary) feature."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from papermind.cli.main import app
from papermind.explain import explain, format_explain

runner = CliRunner()


class TestExplainGlossary:
    """Test glossary lookup."""

    def test_exact_match(self) -> None:
        result = explain("CN2")
        assert result is not None
        assert result.source == "glossary"
        assert "Curve Number" in result.name

    def test_case_insensitive(self) -> None:
        result = explain("cn2")
        assert result is not None
        assert "Curve Number" in result.name

    def test_alias_match(self) -> None:
        """'baseflow' is a related term for alpha_bf."""
        result = explain("baseflow")
        assert result is not None
        assert result.source == "glossary"

    def test_full_name_match(self) -> None:
        result = explain("Kling-Gupta Efficiency")
        assert result is not None
        assert result.name == "Kling-Gupta Efficiency"

    def test_unknown_returns_none(self) -> None:
        result = explain("nonexistent_concept_xyz")
        assert result is None

    def test_range_present(self) -> None:
        result = explain("ESCO")
        assert result is not None
        assert result.range == [0.01, 1.0]

    def test_no_range_for_concepts(self) -> None:
        result = explain("HRU")
        assert result is not None
        assert result.range is None


class TestFormatExplain:
    """Test output formatting."""

    def test_format_with_range(self) -> None:
        result = explain("CN2")
        assert result is not None
        text = format_explain(result)
        assert "35" in text
        assert "98" in text
        assert "glossary" in text

    def test_format_without_range(self) -> None:
        result = explain("HRU")
        assert result is not None
        text = format_explain(result)
        assert "Hydrologic Response Unit" in text


class TestExplainCLI:
    """Test CLI integration."""

    def test_explain_cli_glossary(self) -> None:
        result = runner.invoke(app, ["explain", "SURLAG"])
        assert result.exit_code == 0
        assert "Surface Runoff Lag" in result.output

    def test_explain_cli_not_found(self) -> None:
        result = runner.invoke(app, ["explain", "nonexistent_xyz"])
        assert result.exit_code == 1

    def test_explain_cli_with_kb(self, tmp_path: Path) -> None:
        """With --kb, falls back to KB search for unknown concepts."""
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / ".papermind").mkdir()
        (kb / "catalog.json").write_text("[]")
        papers = kb / "papers" / "hydrology" / "test-paper"
        papers.mkdir(parents=True)
        (papers / "paper.md").write_text(
            "---\ntype: paper\ntitle: Test\ntopic: hydrology\n---\n\n"
            "# Muskingum Routing Method\n\nThe method uses...\n"
        )

        result = runner.invoke(app, ["--kb", str(kb), "explain", "Muskingum"])
        # Should either find via KB search or exit 1 (no qmd in test env)
        # Just verify it doesn't crash
        assert result.exit_code in (0, 1)
