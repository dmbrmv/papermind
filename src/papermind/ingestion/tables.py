"""Table extraction from OCR'd markdown — regex-based, zero deps."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ExtractedTable:
    """A single extracted table from a paper."""

    headers: list[str]
    rows: list[list[str]]
    section: str = ""  # nearest heading
    caption: str = ""  # text immediately before the table

    def to_dict(self) -> dict:
        """Serialize for frontmatter storage."""
        d: dict = {
            "headers": self.headers,
            "rows": self.rows,
        }
        if self.section:
            d["section"] = self.section
        if self.caption:
            d["caption"] = self.caption
        return d

    @property
    def num_rows(self) -> int:
        return len(self.rows)

    @property
    def num_cols(self) -> int:
        return len(self.headers)


_HEADING = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)

# Match a markdown table row: | cell | cell | cell |
_TABLE_ROW = re.compile(r"^\|(.+)\|$")
# Match separator row: | :--- | :--- | or | --- | --- |
_SEPARATOR = re.compile(r"^\|[\s:]*-+[\s:]*(\|[\s:]*-+[\s:]*)+\|$")


def _parse_row(line: str) -> list[str]:
    """Parse a markdown table row into cell values."""
    # Strip outer pipes and split by inner pipes
    inner = line.strip().strip("|")
    return [cell.strip() for cell in inner.split("|")]


def _resolve_section(text: str, position: int) -> str:
    """Find the nearest heading before the given position."""
    best = ""
    for m in _HEADING.finditer(text):
        if m.start() <= position:
            best = m.group(2).strip()
        else:
            break
    return best


def _extract_caption(text: str, table_start: int) -> str:
    """Extract caption text immediately before a table.

    Looks for "Table N:" or "**Table N.**" patterns, or just the
    preceding non-empty line.
    """
    before = text[:table_start].rstrip()
    lines = before.split("\n")

    for line in reversed(lines[-3:]):
        stripped = line.strip()
        if not stripped:
            continue
        # Table caption patterns
        if re.match(r"^(\*\*)?Table\s+\d", stripped, re.IGNORECASE):
            return stripped.strip("*").strip()
        # Any short descriptive line before the table
        if len(stripped) < 200 and not stripped.startswith("|"):
            return stripped
        break
    return ""


def extract_tables(markdown: str) -> list[ExtractedTable]:
    """Extract markdown tables from OCR'd text.

    Detects pipe-delimited markdown tables with header + separator +
    data rows. Returns structured table objects.

    Args:
        markdown: Full markdown text from OCR conversion.

    Returns:
        List of ExtractedTable objects, ordered by position.
    """
    tables: list[ExtractedTable] = []
    lines = markdown.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Look for a table header row (has pipes)
        if not _TABLE_ROW.match(line):
            i += 1
            continue

        # Check if next line is a separator
        if i + 1 >= len(lines) or not _SEPARATOR.match(lines[i + 1].strip()):
            i += 1
            continue

        # Found a table — parse header
        headers = _parse_row(line)
        if len(headers) < 2:
            i += 1
            continue

        # Skip separator
        i += 2

        # Parse data rows
        rows: list[list[str]] = []
        while i < len(lines):
            row_line = lines[i].strip()
            if not _TABLE_ROW.match(row_line):
                break
            cells = _parse_row(row_line)
            # Pad or trim to match header count
            while len(cells) < len(headers):
                cells.append("")
            rows.append(cells[: len(headers)])
            i += 1

        if not rows:
            continue

        # Compute position for section/caption resolution
        # Find where this table starts in the original text
        table_text = line
        pos = markdown.find(table_text)

        section = _resolve_section(markdown, pos) if pos >= 0 else ""
        caption = _extract_caption(markdown, pos) if pos >= 0 else ""

        tables.append(
            ExtractedTable(
                headers=headers,
                rows=rows,
                section=section,
                caption=caption,
            )
        )

    return tables
