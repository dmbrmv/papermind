"""Paper ingestion — PDF → markdown via Marker subprocess."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from hydrofound.catalog.index import CatalogEntry, CatalogIndex
from hydrofound.catalog.render import render_catalog_md
from hydrofound.config import HydroFoundConfig
from hydrofound.ingestion.common import build_frontmatter, generate_id
from hydrofound.ingestion.validation import validate_pdf

logger = logging.getLogger(__name__)


def convert_pdf(path: Path, config: HydroFoundConfig) -> str:
    """Convert PDF to markdown using Marker subprocess.

    Args:
        path: Path to the PDF file.
        config: HydroFound configuration.

    Returns:
        Markdown string.

    Raises:
        FileNotFoundError: If Marker is not installed (command not found).
        RuntimeError: If Marker returns a non-zero exit code or produces no output.
    """
    cmd = [config.marker_path, str(path), "--output_format", "markdown"]
    if config.marker_use_llm:
        cmd.append("--use_llm")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Marker not found at {config.marker_path!r}. "
            "Install it with: pip install marker-pdf"
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            f"Marker failed with exit code {result.returncode}: {result.stderr}"
        )

    # Marker creates a directory <input_stem>/ next to the input file and writes
    # <filename>.md inside it. Check that location first.
    output_dir = path.parent / path.stem
    if output_dir.exists():
        md_files = list(output_dir.glob("*.md"))
        if md_files:
            return md_files[0].read_text()

    # Newer Marker versions may write a .md file directly beside the input.
    md_path = path.with_suffix(".md")
    if md_path.exists():
        return md_path.read_text()

    # Fall back to stdout (some Marker versions stream output).
    if result.stdout.strip():
        return result.stdout

    raise RuntimeError(f"Marker produced no output for {path}")


def extract_metadata(markdown: str) -> dict:
    """Extract metadata from converted markdown content.

    Extracts:
    - ``title``: first ``# `` level-1 heading.
    - ``doi``: first DOI matching ``10.XXXX/...``.
    - ``year``: first 4-digit year in parentheses within the first 2000 characters,
      in the range 1900–2030.

    Args:
        markdown: Markdown text from PDF conversion.

    Returns:
        Dict with zero or more of: title, doi, year.
    """
    metadata: dict = {}

    title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    if title_match:
        metadata["title"] = title_match.group(1).strip()

    doi_match = re.search(r"(10\.\d{4,9}/[^\s]+)", markdown)
    if doi_match:
        metadata["doi"] = doi_match.group(1).rstrip(".,;)")

    year_match = re.search(r"\((\d{4})\)", markdown[:2000])
    if year_match:
        year = int(year_match.group(1))
        if 1900 <= year <= 2030:
            metadata["year"] = year

    return metadata


def ingest_paper(
    pdf_path: Path,
    topic: str,
    kb_path: Path,
    config: HydroFoundConfig,
    *,
    no_reindex: bool = False,
) -> CatalogEntry | None:
    """Full paper ingestion pipeline.

    Validates the PDF, converts it to markdown via Marker, extracts metadata,
    checks for duplicate DOIs (immutable policy), writes the markdown file with
    YAML frontmatter, and updates catalog.json and catalog.md.

    Args:
        pdf_path: Path to PDF file.
        topic: Topic category for the paper.
        kb_path: Knowledge base root.
        config: HydroFound configuration.
        no_reindex: If True, skip qmd reindex after ingestion.

    Returns:
        CatalogEntry if ingested, None if skipped (duplicate DOI).
    """
    import frontmatter

    validate_pdf(pdf_path)

    markdown = convert_pdf(pdf_path, config)

    meta = extract_metadata(markdown)
    title = meta.get("title", pdf_path.stem)
    doi = meta.get("doi", "")
    year = meta.get("year")

    # Immutable policy: same DOI is a no-op.
    catalog = CatalogIndex(kb_path)
    if doi and catalog.has_doi(doi):
        logger.warning("Paper with DOI %r already exists in catalog — skipping.", doi)
        return None

    entry_id = generate_id("paper", title, year=year, kb_path=kb_path)

    topic_dir = kb_path / "papers" / topic
    topic_dir.mkdir(parents=True, exist_ok=True)

    slug = entry_id.removeprefix("paper-")
    md_path = topic_dir / f"{slug}.md"

    fm = build_frontmatter(
        type="paper",
        id=entry_id,
        title=title,
        topic=topic,
        doi=doi,
        **({"year": year} if year is not None else {}),
    )

    post = frontmatter.Post(markdown)
    post.metadata = fm
    md_path.write_text(frontmatter.dumps(post))

    entry = CatalogEntry(
        id=entry_id,
        type="paper",
        title=title,
        path=str(md_path.relative_to(kb_path)),
        topic=topic,
        doi=doi,
        added=fm["added"],
    )
    catalog.add(entry)

    (kb_path / "catalog.md").write_text(render_catalog_md(catalog.entries))

    if not no_reindex:
        _try_qmd_reindex(kb_path, config)

    return entry


def _try_qmd_reindex(kb_path: Path, config: HydroFoundConfig) -> None:
    """Attempt to run qmd reindex; skip silently if qmd is not installed.

    Args:
        kb_path: Knowledge base root.
        config: HydroFound configuration (provides qmd_path).
    """
    import shutil

    qmd = config.qmd_path
    if shutil.which(qmd) is None:
        return

    try:
        subprocess.run(
            [qmd, "reindex", str(kb_path)],
            check=False,
            capture_output=True,
        )
    except OSError:
        pass
