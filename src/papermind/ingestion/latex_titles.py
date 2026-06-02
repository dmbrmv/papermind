"""Decode LaTeX/BibTeX-encoded titles to clean Unicode.

Zotero/BibTeX exports frequently store titles with brace-protection
(``{{Köppen-Geiger}}``), accent escapes (``K\\"oppen`` → Köppen), Cyrillic
command sequences (``\\cyrchar\\CYRR...`` → Р), and LaTeX dashes (``--`` → –).
Left raw, these read poorly and degrade search. This decodes them to
display-ready Unicode.

``pylatexenc`` is an optional dependency: if it is not installed the input is
returned unchanged so importers (e.g. the MCP server) never break.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _decoder():  # type: ignore[no-untyped-def]
    """Return a cached LatexNodes2Text, or None if pylatexenc is absent."""
    try:
        from pylatexenc.latex2text import LatexNodes2Text
    except ImportError:
        return None
    return LatexNodes2Text()


def looks_latex_encoded(title: str) -> bool:
    """True if a title contains LaTeX escapes or BibTeX brace-protection."""
    return "\\" in title or "{" in title


def decode_latex_title(title: str) -> str:
    """Decode a LaTeX/BibTeX-encoded title to Unicode.

    Args:
        title: A title possibly containing LaTeX escapes or BibTeX
            brace-protection.

    Returns:
        The decoded, whitespace-collapsed title. If there is nothing to
        decode, or ``pylatexenc`` is unavailable, the input is returned
        unchanged (with whitespace collapsed when decoding ran).
    """
    if not looks_latex_encoded(title):
        return title
    decoder = _decoder()
    if decoder is None:
        return title
    decoded = decoder.latex_to_text(title)
    return " ".join(decoded.split()).strip()
