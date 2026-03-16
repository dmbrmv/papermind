"""Tests for papermind watch — concept extraction and KB matching."""

from __future__ import annotations

from pathlib import Path

from papermind.watch import (
    _split_identifier,
    extract_concepts,
    format_watch_output,
    watch_file,
)


class TestSplitIdentifier:
    """Tests for CamelCase and snake_case splitting."""

    def test_camel_case(self) -> None:
        assert "soil" in _split_identifier("SoilWaterBalance")
        assert "water" in _split_identifier("SoilWaterBalance")
        assert "balance" in _split_identifier("SoilWaterBalance")

    def test_snake_case(self) -> None:
        assert "calibration" in _split_identifier("run_calibration")

    def test_filters_stopwords(self) -> None:
        # "self" and "int" are stopwords
        assert _split_identifier("self") == []
        assert _split_identifier("int") == []

    def test_short_tokens_filtered(self) -> None:
        # 2-char tokens should be filtered
        assert _split_identifier("do") == []


class TestExtractConcepts:
    """Tests for AST-based concept extraction."""

    def test_extracts_imports(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("import torch\nfrom numpy import array\n")
        concepts = extract_concepts(f)
        assert "torch" in concepts
        assert "numpy" in concepts

    def test_extracts_function_names(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("def compute_baseflow(params):\n    pass\n")
        concepts = extract_concepts(f)
        assert "compute" in concepts or "baseflow" in concepts

    def test_extracts_class_names(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("class GroundwaterModule:\n    pass\n")
        concepts = extract_concepts(f)
        assert "groundwater" in concepts

    def test_extracts_docstrings(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text('def foo():\n    """Calculate evapotranspiration."""\n    pass\n')
        concepts = extract_concepts(f)
        assert "evapotranspiration" in concepts

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        assert extract_concepts(f) == []

    def test_non_python_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.f90"
        f.write_text("! Fortran comment about groundwater\n")
        concepts = extract_concepts(f)
        # Should use regex fallback for non-Python
        assert isinstance(concepts, list)

    def test_syntax_error_falls_back(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("def broken(\n")
        concepts = extract_concepts(f)
        assert isinstance(concepts, list)  # doesn't crash

    def test_deduplicates(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("import torch\nimport torch\ndef torch_model():\n    pass\n")
        concepts = extract_concepts(f)
        assert concepts.count("torch") == 1


class TestWatchFile:
    """Integration test for watch_file."""

    def test_returns_results(self, tmp_path: Path) -> None:
        # Create a minimal KB
        kb = tmp_path / "kb"
        (kb / "papers" / "hydrology").mkdir(parents=True)
        (kb / "papers" / "hydrology" / "swat.md").write_text(
            "---\ntitle: SWAT Calibration\ntopic: hydrology\n---\n"
            "SWAT model calibration using optimization.\n"
        )

        # Create a source file that mentions calibration
        src = tmp_path / "optimizer.py"
        src.write_text(
            "from optuna import create_study\n"
            "def run_calibration(params):\n"
            '    """Optimize SWAT parameters."""\n'
            "    pass\n"
        )

        results = watch_file(src, kb, limit=5)
        assert isinstance(results, list)

    def test_no_matches(self, tmp_path: Path) -> None:
        kb = tmp_path / "kb"
        kb.mkdir()
        src = tmp_path / "hello.py"
        src.write_text("print('hello')\n")
        results = watch_file(src, kb, limit=5)
        assert results == []


class TestFormatWatchOutput:
    """Tests for output formatting."""

    def test_no_matches(self) -> None:
        output = format_watch_output("test.py", [])
        assert "no matches" in output

    def test_with_matches(self) -> None:
        from papermind.query.fallback import SearchResult

        results = [
            SearchResult(
                path="papers/hydrology/swat.md",
                title="SWAT Paper",
                snippet="...",
                score=5.0,
            )
        ]
        output = format_watch_output("test.py", results)
        assert "1 match" in output
        assert "SWAT Paper" in output
        assert "5.0" in output
