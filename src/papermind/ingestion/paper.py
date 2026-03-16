"""Paper ingestion — PDF → markdown via GLM-OCR."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from papermind.catalog.index import CatalogEntry, CatalogIndex
from papermind.catalog.render import render_catalog_md
from papermind.config import PaperMindConfig
from papermind.ingestion.common import build_frontmatter, generate_id
from papermind.ingestion.validation import validate_pdf

logger = logging.getLogger(__name__)


def convert_pdf(
    path: Path,
    config: PaperMindConfig,
) -> str:
    """Convert PDF to markdown using GLM-OCR.

    Args:
        path: Path to the PDF file.
        config: PaperMind configuration.

    Returns:
        Markdown string.

    Raises:
        ImportError: If GLM-OCR deps are not installed.
        RuntimeError: If conversion fails.
    """
    from papermind.ingestion.glm_ocr import convert_pdf_glm

    return convert_pdf_glm(
        path,
        model_name=config.ocr_model,
        dpi=config.ocr_dpi,
    )


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
    else:
        # GLM-OCR often outputs the title as plain text (no # heading).
        # Use the first non-empty line that looks like a title (>10 chars,
        # starts with uppercase, doesn't look like metadata).
        for line in markdown.split("\n"):
            line = line.strip()
            if (
                len(line) > 10
                and not line.startswith("#")
                and not line.startswith("10.")
                and not line.startswith("http")
                and not line.startswith("---")
                and not re.match(r"^\d{4}", line)
                and not re.match(r"^[a-z]", line)
                and re.match(r"^[A-Z]", line)
            ):
                metadata["title"] = line[:200]
                break

    doi_match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", markdown)
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
    config: PaperMindConfig,
    *,
    no_reindex: bool = False,
    abstract: str = "",
) -> CatalogEntry | None:
    """Full paper ingestion pipeline.

    Validates the PDF, converts it to markdown via GLM-OCR, extracts metadata,
    checks for duplicate DOIs (immutable policy), writes the markdown file with
    YAML frontmatter, and updates catalog.json and catalog.md.

    Args:
        pdf_path: Path to PDF file.
        topic: Topic category for the paper.
        kb_path: Knowledge base root.
        config: PaperMind configuration.
        no_reindex: If True, skip qmd reindex after ingestion.
        abstract: Optional abstract from discovery (stored in frontmatter).

    Returns:
        CatalogEntry if ingested, None if skipped (duplicate DOI).
    """
    import frontmatter

    validate_pdf(pdf_path)

    # First pass: OCR without images to get metadata for path resolution
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

    # Title similarity dedup: skip papers that look like near-duplicates.
    from difflib import SequenceMatcher

    for existing in catalog.entries:
        if existing.type == "paper" and existing.title:
            ratio = SequenceMatcher(None, title.lower(), existing.title.lower()).ratio()
            if ratio > 0.9:
                logger.warning(
                    "Similar paper already exists: %r (%.0f%% match) — skipping.",
                    existing.title,
                    ratio * 100,
                )
                return None

    entry_id = generate_id("paper", title, year=year, kb_path=kb_path)

    topic_dir = kb_path / "papers" / topic
    topic_dir.mkdir(parents=True, exist_ok=True)

    slug = entry_id.removeprefix("paper-")
    md_path = topic_dir / f"{slug}.md"

    # Extract embedded images (figures, charts) — best effort
    try:
        from papermind.ingestion.glm_ocr import extract_images

        image_dir = topic_dir / slug
        image_files = extract_images(pdf_path, image_dir)
        if image_files:
            markdown += "\n\n---\n\n## Figures\n\n"
            for img_name in image_files:
                markdown += f"![{img_name}]({slug}/{img_name})\n\n"
    except Exception:  # noqa: BLE001
        logger.debug("Image extraction skipped for %s", pdf_path.name)

    fm = build_frontmatter(
        type="paper",
        id=entry_id,
        title=title,
        topic=topic,
        doi=doi,
        **({"year": year} if year is not None else {}),
        **({"abstract": abstract} if abstract else {}),
    )

    post = frontmatter.Post(markdown)
    post.metadata = fm
    md_path.write_text(frontmatter.dumps(post))

    # Copy source PDF alongside the markdown for easy comparison
    import shutil

    pdf_copy = topic_dir / f"{slug}.pdf"
    if not pdf_copy.exists():
        shutil.copy2(pdf_path, pdf_copy)

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
        from papermind.query.qmd import qmd_reindex

        qmd_reindex(kb_path)

    return entry


class BatchResult:
    """Summary of a batch paper ingestion run.

    Attributes:
        ingested: Number of papers successfully ingested.
        skipped: Number of papers skipped (duplicate DOI).
        failed: Number of papers that raised an error during ingestion.
        errors: Mapping of PDF path to error message for each failure.
    """

    def __init__(self) -> None:
        self.ingested: int = 0
        self.skipped: int = 0
        self.failed: int = 0
        self.errors: dict[Path, str] = {}

    def __str__(self) -> str:
        return f"{self.ingested} ingested, {self.skipped} skipped, {self.failed} failed"


def ingest_papers_batch(
    folder: Path,
    topic: str,
    kb_path: Path,
    config: PaperMindConfig,
) -> BatchResult:
    """Ingest all PDF files in *folder* into the knowledge base.

    Walks *folder* recursively for ``*.pdf`` files.  Each file is processed
    individually; errors are logged and counted rather than propagated so that
    the remaining files are always attempted.  A single qmd reindex is issued
    at the end (not once per file).

    Duplicate-DOI detection follows the same immutable policy as
    :func:`ingest_paper`: a paper whose DOI already exists in the catalog is
    silently skipped and counted as *skipped*.

    Args:
        folder: Directory to walk for ``*.pdf`` files.
        topic: Topic category applied to every ingested paper.
        kb_path: Knowledge base root.
        config: PaperMind configuration.

    Returns:
        :class:`BatchResult` with ingested / skipped / failed counts.
    """
    result = BatchResult()

    pdf_paths = sorted(folder.rglob("*.pdf"))
    logger.info("Batch ingestion: found %d PDF(s) in %s", len(pdf_paths), folder)

    for pdf_path in pdf_paths:
        try:
            entry = ingest_paper(
                pdf_path,
                topic,
                kb_path,
                config,
                no_reindex=True,  # Reindex once at end of batch
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to ingest %s: %s", pdf_path.name, exc)
            result.failed += 1
            result.errors[pdf_path] = str(exc)
            continue

        if entry is None:
            logger.info("Skipped %s (duplicate DOI).", pdf_path.name)
            result.skipped += 1
        else:
            logger.info("Ingested %s as %r.", pdf_path.name, entry.id)
            result.ingested += 1

    # Single reindex at end of batch (only if anything was actually ingested).
    if result.ingested > 0:
        from papermind.query.qmd import qmd_reindex

        qmd_reindex(kb_path)

    logger.info("Batch complete: %s", result)
    return result
