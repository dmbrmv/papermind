"""Tests for LaTeX/HTML title + abstract cleaning helpers."""

from __future__ import annotations

import pytest

from papermind.ingestion.latex_titles import (
    clean_body_heading,
    clean_scientific_text,
    decode_latex_title,
    looks_html_junk,
    looks_latex_encoded,
    strip_html,
)

# ---------------------------------------------------------------------------
# detectors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Plain ASCII title", False),
        (r"K\"oppen-Geiger", True),
        ("{{Brace Protected}}", True),
        ("nothing special", False),
    ],
)
def test_looks_latex_encoded(text: str, expected: bool) -> None:
    assert looks_latex_encoded(text) is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Q<sub>flow</sub> prediction", True),
        ("$<$}p{$>$}Abstract.{$<$}/p{$>$}", True),
        ("entity &amp; here", True),
        ("Series <<Earth Sciences>>", False),  # guillemets are NOT html
        ("plain prose with no markup", False),
    ],
)
def test_looks_html_junk(text: str, expected: bool) -> None:
    assert looks_html_junk(text) is expected


# ---------------------------------------------------------------------------
# strip_html — whitelist only, entities unescaped
# ---------------------------------------------------------------------------


def test_strip_html_removes_whitelisted_tags() -> None:
    assert strip_html("Q<sub>flow</sub>") == "Qflow"


def test_strip_html_preserves_guillemets() -> None:
    # bare << >> are not whitelisted tags and must survive
    assert strip_html("Series <<Earth Sciences>>") == "Series <<Earth Sciences>>"


def test_strip_html_unescapes_entities() -> None:
    assert strip_html("T &gt; 0 &amp; valid") == "T > 0 & valid"


# ---------------------------------------------------------------------------
# clean_scientific_text — full pipeline
# ---------------------------------------------------------------------------


def test_clean_passes_through_plain_text() -> None:
    assert clean_scientific_text("A plain abstract.") == "A plain abstract."


def test_clean_empty_string() -> None:
    assert clean_scientific_text("") == ""


def test_clean_decodes_latex_escaped_html() -> None:
    pytest.importorskip("pylatexenc")
    raw = (
        '$<$}p{$><$}strong class="journal-contentHeaderColor"{$>$}'
        "Abstract.{$<$}/strong{$>$} The glacier coverage changed."
    )
    out = clean_scientific_text(raw)
    assert out == "Abstract. The glacier coverage changed."
    assert "$" not in out and "<" not in out and "{" not in out


def test_clean_strips_plain_html_tag() -> None:
    out = clean_scientific_text("Streamflow (Q<sub>flow</sub>) prediction.")
    assert out == "Streamflow (Qflow) prediction."


def test_clean_decodes_latex_accents_and_math() -> None:
    pytest.importorskip("pylatexenc")
    out = clean_scientific_text(
        r"Surface runoff $Q = k \cdot P^{2}$ with K\"oppen forcing."
    )
    assert "Köppen" in out
    assert "\\" not in out


def test_clean_passes_through_plain_text_with_odd_whitespace() -> None:
    # plain text (no LaTeX/HTML) is left untouched to keep the B1 mutation
    # footprint minimal — whitespace is only collapsed when cleaning runs
    assert clean_scientific_text("a   b\n\nc") == "a   b\n\nc"


def test_clean_collapses_whitespace_when_stripping_html() -> None:
    assert clean_scientific_text("Q<sub>flow</sub>   model") == "Qflow model"


def test_decode_latex_title_unchanged_for_plain() -> None:
    assert decode_latex_title("Plain Title") == "Plain Title"


# ---------------------------------------------------------------------------
# clean_body_heading — the leading body H1 is what qmd shows as the result title
# ---------------------------------------------------------------------------


def test_clean_body_heading_strips_html_h1() -> None:
    out, changed = clean_body_heading(
        "# Streamflow (Q<sub>flow</sub>) Model\n\nBody.\n"
    )
    assert changed
    assert out.startswith("# Streamflow (Qflow) Model")
    assert "<sub>" not in out


def test_clean_body_heading_unchanged_for_clean_h1() -> None:
    content = "# A Perfectly Clean Title\n\nBody.\n"
    out, changed = clean_body_heading(content)
    assert not changed
    assert out == content


def test_clean_body_heading_only_touches_first_line() -> None:
    # Encoded markup below the first real line must be left alone — a body
    # section heading is not the title qmd surfaces.
    content = "Intro paragraph.\n\n# Streamflow (Q<sub>flow</sub>)\n"
    out, changed = clean_body_heading(content)
    assert not changed
    assert out == content


def test_clean_body_heading_skips_leading_blank_lines() -> None:
    out, changed = clean_body_heading("\n\n# Streamflow (Q<sub>flow</sub>)\n")
    assert changed
    assert "# Streamflow (Qflow)" in out
