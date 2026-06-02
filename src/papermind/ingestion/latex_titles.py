"""Clean LaTeX/BibTeX/HTML-encoded titles and abstracts to readable Unicode.

Zotero/BibTeX exports frequently store titles with brace-protection
(``{{Köppen-Geiger}}``), accent escapes (``K\\"oppen`` → Köppen), Cyrillic
command sequences (``\\cyrchar\\CYRR...`` → Р), and LaTeX dashes (``--`` → –).
Abstracts additionally carry publisher HTML — both plain (``Q<sub>flow</sub>``)
and LaTeX-escaped (``$<$}p{$><$}strong class="..."{$>$}`` for ``<p><strong …>``).
Left raw, these read poorly and degrade search. The helpers here decode them to
display-ready Unicode:

* :func:`decode_latex_title` — LaTeX-only decode, for titles.
* :func:`clean_scientific_text` — LaTeX decode **then** HTML strip, for abstracts
  (and any field that may carry both). Order matters: LaTeX is decoded first so
  that LaTeX-escaped angle brackets become real tags the HTML pass can remove.

``pylatexenc`` is an optional dependency: if it is not installed the LaTeX step
is skipped (input passed through) so importers (e.g. the MCP server) never break.
"""

from __future__ import annotations

import html
import re
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


# Whitelist of real HTML tag names seen in publisher abstracts. A whitelist
# (not a generic ``<...>`` strip) is essential: bare ``<<Earth Sciences>>``
# guillemets and stray ``<`` must NOT be mistaken for tags and delete real words.
_HTML_TAGS = (
    "p|strong|em|i|b|br|span|div|a|ul|ol|li|h[1-6]|sub|sup|table|tr|td|th|"
    "thead|tbody|sec|title|abstract|inline-formula|disp-formula|xref|italic|"
    "bold|sc|monospace|underline|caption|fig|label|mml:math|tex-math"
)
_HTML_TAG_RE = re.compile(rf"</?(?:{_HTML_TAGS})\b[^>]*>", re.IGNORECASE)
# LaTeX-escaped HTML (``$<$``/``$>$``/``{$``) and HTML entities (``&amp;``).
_HTML_JUNK_RE = re.compile(r"\$<\$|\$>\$|\{\$|&[a-zA-Z]+;|&#\d+;")


def looks_html_junk(text: str) -> bool:
    """True if text carries HTML tags/entities or LaTeX-escaped HTML."""
    return bool(_HTML_TAG_RE.search(text) or _HTML_JUNK_RE.search(text))


def strip_html(text: str) -> str:
    """Remove whitelisted HTML tags and unescape HTML entities.

    Tags are removed before entities are unescaped so that entity-encoded
    literals (``T &gt; 0``) survive as their characters rather than being
    re-interpreted as tags.
    """
    text = _HTML_TAG_RE.sub("", text)
    return html.unescape(text)


def clean_scientific_text(text: str) -> str:
    """Decode LaTeX and strip HTML from a title/abstract to clean Unicode.

    Pipeline: LaTeX-decode first (so LaTeX-escaped HTML like ``$<$}p{$>`` becomes
    real ``<p>`` tags), then strip whitelisted HTML tags and unescape entities,
    then collapse whitespace.

    Args:
        text: A title or abstract possibly carrying LaTeX and/or HTML encoding.

    Returns:
        The cleaned, whitespace-collapsed text. Input is returned unchanged when
        there is nothing to clean; the LaTeX step is skipped (HTML still stripped)
        when ``pylatexenc`` is unavailable.
    """
    if not text:
        return text
    needs_latex = looks_latex_encoded(text)
    if not (needs_latex or looks_html_junk(text)):
        return text
    out = text
    if needs_latex:
        decoder = _decoder()
        if decoder is not None:
            out = decoder.latex_to_text(out)
    out = strip_html(out)
    return " ".join(out.split()).strip()
