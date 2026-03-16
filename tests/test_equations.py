"""Tests for equation extraction from OCR'd markdown."""

from __future__ import annotations

from papermind.ingestion.equations import (
    Equation,
    _is_math_content,
    _resolve_section,
    extract_equations,
)


class TestIsMathContent:
    """Filter for real math vs accidental $ usage."""

    def test_equation_with_equals(self) -> None:
        assert _is_math_content("x = y + z")

    def test_equation_with_frac(self) -> None:
        assert _is_math_content("\\frac{a}{b}")

    def test_equation_with_subscript(self) -> None:
        assert _is_math_content("x_{i}")

    def test_currency_rejected(self) -> None:
        assert not _is_math_content("5")

    def test_single_word_rejected(self) -> None:
        assert not _is_math_content("hello")

    def test_short_rejected(self) -> None:
        assert not _is_math_content("x")


class TestResolveSection:
    """Find nearest heading before a position."""

    def test_finds_heading(self) -> None:
        text = "## Introduction\n\nSome text.\n\n## Methods\n\nMore text."
        assert _resolve_section(text, 40) == "Methods"

    def test_first_heading(self) -> None:
        text = "## Intro\n\nContent here."
        assert _resolve_section(text, 15) == "Intro"

    def test_no_heading(self) -> None:
        text = "Just plain text."
        assert _resolve_section(text, 5) == ""


class TestExtractEquations:
    """Core equation extraction."""

    def test_display_equation(self) -> None:
        md = "## Methods\n\n$$Q = K \\cdot A$$\n\n(1)\n"
        eqs = extract_equations(md)
        display = [e for e in eqs if e.display]
        assert len(display) >= 1
        assert "Q = K" in display[0].latex

    def test_display_equation_number(self) -> None:
        md = "$$x = y$$\n\n(1)\n\nSome text.\n\n$$a = b$$\n\n(2)\n"
        eqs = extract_equations(md)
        display = [e for e in eqs if e.display]
        assert display[0].number == "1"
        assert display[1].number == "2"

    def test_inline_equation(self) -> None:
        md = "The variable $x_{i} = 5$ is important.\n"
        eqs = extract_equations(md)
        inline = [e for e in eqs if not e.display]
        assert len(inline) >= 1

    def test_inline_filters_non_math(self) -> None:
        md = "The cost is $5 per unit.\n"
        eqs = extract_equations(md)
        assert len(eqs) == 0

    def test_section_context(self) -> None:
        md = "## Results\n\n$$E = mc^2$$\n"
        eqs = extract_equations(md)
        assert eqs[0].section == "Results"

    def test_empty_text(self) -> None:
        assert extract_equations("") == []

    def test_no_equations(self) -> None:
        md = "# Introduction\n\nThis paper has no math.\n"
        assert extract_equations(md) == []

    def test_multiline_display(self) -> None:
        md = "$$\nQ = \\sum_{i=1}^{n} q_i\n$$\n\n(3)\n"
        eqs = extract_equations(md)
        display = [e for e in eqs if e.display]
        assert len(display) >= 1
        assert "sum" in display[0].latex

    def test_equation_to_dict(self) -> None:
        eq = Equation(
            latex="Q = K",
            number="1",
            display=True,
            section="Methods",
            context="flow equation",
        )
        d = eq.to_dict()
        assert d["latex"] == "Q = K"
        assert d["number"] == "1"
        assert d["section"] == "Methods"
