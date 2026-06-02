"""Tests for KB integrity content-quality checks (encoded title/abstract)."""

from __future__ import annotations

from papermind.integrity import validate_paper_metadata


def _valid(**overrides) -> dict:
    """A structurally valid paper metadata dict, with optional overrides."""
    meta = {
        "type": "paper",
        "id": "paper-x",
        "title": "A Clean Readable Title",
        "topic": "hydrology",
    }
    meta.update(overrides)
    return meta


def _codes(meta: dict) -> set[str]:
    return {f.code for f in validate_paper_metadata(meta)}


def test_clean_paper_has_no_quality_warnings() -> None:
    codes = _codes(_valid(abstract="A perfectly clean abstract about runoff."))
    quality = {
        "latex_encoded_title",
        "placeholder_title",
        "latex_encoded_abstract",
        "html_junk_abstract",
    }
    assert codes.isdisjoint(quality)


def test_latex_encoded_title_flagged() -> None:
    assert "latex_encoded_title" in _codes(_valid(title=r"K\"oppen Classification"))


def test_brace_protected_title_flagged() -> None:
    assert "latex_encoded_title" in _codes(_valid(title="{{Brace Protected}}"))


def test_placeholder_title_flagged() -> None:
    assert "placeholder_title" in _codes(_valid(title="Abstract"))


def test_placeholder_title_case_insensitive() -> None:
    assert "placeholder_title" in _codes(_valid(title="Introduction"))


def test_latex_encoded_abstract_flagged() -> None:
    codes = _codes(_valid(abstract=r"Runoff scales as $Q = k \cdot P$ here."))
    assert "latex_encoded_abstract" in codes


def test_html_junk_abstract_flagged() -> None:
    codes = _codes(_valid(abstract="Streamflow Q<sub>flow</sub> prediction."))
    assert "html_junk_abstract" in codes


def test_quality_findings_are_warnings_not_errors() -> None:
    findings = validate_paper_metadata(_valid(title="Abstract"))
    placeholder = [f for f in findings if f.code == "placeholder_title"]
    assert placeholder and placeholder[0].severity == "warning"
