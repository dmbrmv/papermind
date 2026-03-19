"""Equation extraction from OCR'd markdown — regex-based, zero deps."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Equation:
    """A single extracted equation."""

    latex: str
    number: str = ""  # e.g. "1", "2.3", "A.1"
    display: bool = True  # True for $$...$$, False for $...$
    section: str = ""  # nearest heading
    context: str = ""  # surrounding text

    def to_dict(self) -> dict:
        """Serialize for frontmatter storage."""
        d: dict = {"latex": self.latex, "display": self.display}
        if self.number:
            d["number"] = self.number
        if self.section:
            d["section"] = self.section
        if self.context:
            d["context"] = self.context
        return d


# Regex patterns
_DISPLAY_EQ = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)
_INLINE_EQ = re.compile(r"(?<!\$)\$([^$\n]+?)\$(?!\$)")
_EQ_NUMBER = re.compile(r"^\((\d+(?:\.\d+)*|[A-Z]\.\d+)\)\s*$", re.MULTILINE)
_HEADING = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)

# Math indicators for filtering inline equations
_MATH_INDICATORS = frozenset(
    "= \\ _ ^ \\frac \\sum \\int \\partial \\nabla "
    "\\mathbb \\text \\left \\right \\cdot \\times "
    "\\alpha \\beta \\gamma \\delta \\epsilon \\theta "
    "\\lambda \\mu \\sigma \\omega \\phi \\psi".split()
)


_CITATION_REF = re.compile(r"^\^?\{?[\d,\s-]+\}?$")


def _is_math_content(s: str) -> bool:
    """Distinguish real math from accidental $ usage or citations."""
    s = s.strip()
    if len(s) < 2:
        return False
    # Filter out citation references like ^{1,2} or {10-12}
    if _CITATION_REF.match(s):
        return False
    return any(ind in s for ind in _MATH_INDICATORS) or bool(re.search(r"[a-z]_\{", s))


def _resolve_section(text: str, position: int) -> str:
    """Find the nearest heading before the given position."""
    best = ""
    for m in _HEADING.finditer(text):
        if m.start() <= position:
            best = m.group(2).strip()
        else:
            break
    return best


def _extract_context(text: str, position: int, chars: int = 120) -> str:
    """Grab surrounding text for search context."""
    start = max(0, position - chars // 2)
    end = min(len(text), position + chars // 2)
    ctx = text[start:end].strip()
    # Remove LaTeX delimiters from context
    ctx = ctx.replace("$$", "").replace("$", "")
    # Collapse whitespace
    ctx = re.sub(r"\s+", " ", ctx)
    return ctx[:chars]


def extract_equations(markdown: str) -> list[Equation]:
    """Extract equations from OCR'd markdown.

    Finds display equations ($$...$$) and inline equations ($...$),
    associates equation numbers, and captures section context.

    Args:
        markdown: Full markdown text from OCR conversion.

    Returns:
        List of Equation objects, ordered by position in text.
    """
    equations: list[Equation] = []

    # Find all equation numbers and their positions
    eq_numbers: dict[int, str] = {}
    for m in _EQ_NUMBER.finditer(markdown):
        eq_numbers[m.start()] = m.group(1)

    # Display equations ($$...$$)
    for m in _DISPLAY_EQ.finditer(markdown):
        latex = m.group(1).strip()
        if not latex or len(latex) < 3:
            continue

        # Look for equation number after this block
        number = ""
        search_start = m.end()
        for pos, num in eq_numbers.items():
            if search_start <= pos <= search_start + 20:
                number = num
                break

        section = _resolve_section(markdown, m.start())
        context = _extract_context(markdown, m.start())

        equations.append(
            Equation(
                latex=latex,
                number=number,
                display=True,
                section=section,
                context=context,
            )
        )

    # Inline equations ($...$)
    for m in _INLINE_EQ.finditer(markdown):
        latex = m.group(1).strip()
        if not _is_math_content(latex):
            continue
        if len(latex) < 3:
            continue

        # Skip if this is inside a display equation we already found
        if any(
            eq.display
            and m.start() > markdown.find(f"$${eq.latex}$$")
            and m.end() < markdown.find(f"$${eq.latex}$$") + len(eq.latex) + 4
            for eq in equations
        ):
            continue

        section = _resolve_section(markdown, m.start())
        equations.append(
            Equation(
                latex=latex,
                number="",
                display=False,
                section=section,
                context="",  # skip context for inline
            )
        )

    return equations
