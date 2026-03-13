"""Tests for file validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from hydrofound.ingestion.validation import ValidationError, validate_pdf


def test_valid_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake pdf content " * 100)
    validate_pdf(pdf)  # should not raise


def test_invalid_magic_bytes(tmp_path: Path) -> None:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"<html>not a pdf</html>" * 100)
    with pytest.raises(ValidationError, match="magic bytes"):
        validate_pdf(pdf)


def test_too_small(tmp_path: Path) -> None:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4")  # < 1KB
    with pytest.raises(ValidationError, match="too small"):
        validate_pdf(pdf)


def test_too_large(tmp_path: Path) -> None:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4" + b"\x00" * (201 * 1024 * 1024))
    with pytest.raises(ValidationError, match="too large"):
        validate_pdf(pdf)


def test_nonexistent_file(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="not found"):
        validate_pdf(tmp_path / "nonexistent.pdf")


def test_null_byte_in_filename(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="control character"):
        validate_pdf(tmp_path / "bad\x00file.pdf")


def test_control_chars_in_filename(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="control character"):
        validate_pdf(tmp_path / "bad\nfile.pdf")
