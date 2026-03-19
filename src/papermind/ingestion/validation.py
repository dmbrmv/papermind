"""File validation — magic bytes, size bounds, safety checks."""

from __future__ import annotations

from pathlib import Path

MIN_PDF_SIZE = 1024  # 1 KB
MAX_PDF_SIZE = 200 * 1024 * 1024  # 200 MB
PDF_MAGIC = b"%PDF-"

MIN_MD_SIZE = 10  # 10 bytes — must have *some* content
MAX_MD_SIZE = 50 * 1024 * 1024  # 50 MB


class ValidationError(Exception):
    """Raised when file validation fails."""


def validate_pdf(path: Path) -> None:
    """Validate that a file is a plausible PDF.

    Args:
        path: Path to the file to validate.

    Raises:
        ValidationError: If the file is not a valid PDF.
    """
    # Check for null bytes and control characters in filename
    name = path.name
    if any(ord(c) < 32 for c in name) or "\x00" in str(path):
        raise ValidationError(f"Filename contains control character: {name!r}")

    if not path.exists():
        raise ValidationError(f"File not found: {path}")

    size = path.stat().st_size
    if size < MIN_PDF_SIZE:
        raise ValidationError(
            f"File too small ({size} bytes, minimum {MIN_PDF_SIZE}): {path.name}"
        )
    if size > MAX_PDF_SIZE:
        raise ValidationError(
            f"File too large ({size // (1024 * 1024)} MB, "
            f"maximum {MAX_PDF_SIZE // (1024 * 1024)} MB): {path.name}"
        )

    with open(path, "rb") as f:
        header = f.read(5)
    if not header.startswith(PDF_MAGIC):
        raise ValidationError(
            f"Invalid PDF magic bytes (expected %PDF-, got {header!r}): {path.name}"
        )


def validate_markdown(path: Path) -> None:
    """Validate that a file is a plausible markdown document.

    Args:
        path: Path to the file to validate.

    Raises:
        ValidationError: If the file is not a valid markdown file.
    """
    name = path.name
    if any(ord(c) < 32 for c in name) or "\x00" in str(path):
        raise ValidationError(f"Filename contains control character: {name!r}")

    if not path.exists():
        raise ValidationError(f"File not found: {path}")

    if path.suffix.lower() not in (".md", ".markdown"):
        raise ValidationError(
            f"Not a markdown file (expected .md or .markdown): {name}"
        )

    size = path.stat().st_size
    if size < MIN_MD_SIZE:
        raise ValidationError(
            f"File too small ({size} bytes, minimum {MIN_MD_SIZE}): {name}"
        )
    if size > MAX_MD_SIZE:
        raise ValidationError(
            f"File too large ({size // (1024 * 1024)} MB, "
            f"maximum {MAX_MD_SIZE // (1024 * 1024)} MB): {name}"
        )
