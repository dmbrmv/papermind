"""Paper ingestion — PDF → markdown via GLM-OCR, or direct markdown ingest."""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

from papermind.catalog.index import CatalogEntry, CatalogIndex
from papermind.catalog.render import render_catalog_md
from papermind.config import PaperMindConfig
from papermind.ingestion.common import build_frontmatter, generate_id
from papermind.ingestion.validation import ValidationError, validate_markdown, validate_pdf
from papermind.integrity import validate_paper_metadata

logger = logging.getLogger(__name__)

_MARKDOWN_EXTENSIONS = {".md", ".markdown"}


def convert_pdf(
    path: Path,
    config: PaperMindConfig,
) -> str:
    """Convert PDF to markdown using the configured OCR backend.

    Args:
        path: Path to the PDF file.
        config: PaperMind configuration.

    Returns:
        Markdown string.

    Raises:
        ImportError: If local OCR deps are not installed.
        RuntimeError: If conversion fails.
    """
    from papermind.ingestion.ocr_backend import convert_pdf_with_backend

    return convert_pdf_with_backend(path, config)


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

    primary_window = _primary_metadata_window(markdown)

    doi_match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", primary_window)
    if doi_match:
        metadata["doi"] = doi_match.group(1).rstrip(".,;)")

    year_match = re.search(r"\((\d{4})\)", primary_window[:4000])
    if year_match:
        year = int(year_match.group(1))
        if 1900 <= year <= 2030:
            metadata["year"] = year

    return metadata


def _primary_metadata_window(markdown: str) -> str:
    """Return the early body region where paper metadata normally appears."""
    window = markdown[:8000]
    refs_match = re.search(
        r"(?im)^(#{0,3}\s*)?(references|bibliography)\b",
        window,
    )
    if refs_match:
        window = window[: refs_match.start()]
    return window


def _title_similarity(left: str, right: str) -> float:
    """Approximate similarity between two titles."""
    normalize = lambda s: re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s.lower())).strip()
    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def _read_markdown_source(path: Path) -> tuple[str, dict]:
    """Read a markdown file, separating content from any existing frontmatter.

    Args:
        path: Path to the markdown file.

    Returns:
        Tuple of (markdown_body, frontmatter_metadata).
    """
    import frontmatter as fm_lib

    post = fm_lib.load(path)
    return post.content, dict(post.metadata)


def ingest_paper(
    source_path: Path,
    topic: str,
    kb_path: Path,
    config: PaperMindConfig,
    *,
    no_reindex: bool = False,
    abstract: str = "",
    cites: list[str] | None = None,
    cited_by: list[str] | None = None,
    preferred_title: str = "",
    preferred_doi: str = "",
    preferred_year: int | None = None,
) -> CatalogEntry | None:
    """Full paper ingestion pipeline.

    Accepts PDF files (converted via GLM-OCR) or markdown files (ingested
    directly).  For markdown input, existing YAML frontmatter is respected —
    title, DOI, year, and abstract are read from it when present.

    Args:
        source_path: Path to PDF or markdown file.
        topic: Topic category for the paper.
        kb_path: Knowledge base root.
        config: PaperMind configuration.
        no_reindex: If True, skip qmd reindex after ingestion.
        abstract: Optional abstract from discovery (stored in frontmatter).
        cites: DOIs of papers referenced by this paper (from Semantic Scholar).
        cited_by: DOIs of papers that cite this paper (from Semantic Scholar).

    Returns:
        CatalogEntry if ingested, None if skipped (duplicate DOI).
    """
    import frontmatter

    is_markdown = source_path.suffix.lower() in _MARKDOWN_EXTENSIONS

    if is_markdown:
        validate_markdown(source_path)
        markdown, existing_fm = _read_markdown_source(source_path)
    else:
        validate_pdf(source_path)
        markdown = convert_pdf(source_path, config)
        existing_fm = {}

    # Extract metadata from markdown body (regex-based)
    meta = extract_metadata(markdown)

    # Existing frontmatter takes precedence over regex extraction
    extracted_title = meta.get("title", "")
    extracted_doi = meta.get("doi", "")
    extracted_year = meta.get("year")

    if preferred_title and extracted_title:
        similarity = _title_similarity(preferred_title, extracted_title)
        if similarity < 0.75:
            raise ValidationError(
                "Downloaded PDF title does not match discovered paper metadata: "
                f"preferred={preferred_title!r}, extracted={extracted_title!r}"
            )

    title = existing_fm.get("title") or preferred_title or extracted_title or source_path.stem
    doi = existing_fm.get("doi") or preferred_doi or extracted_doi
    year = existing_fm.get("year") or preferred_year or extracted_year
    if not abstract:
        abstract = existing_fm.get("abstract", "")

    if preferred_doi and extracted_doi and preferred_doi != extracted_doi:
        logger.warning(
            "OCR-extracted DOI differs from discovered DOI for %s: extracted=%s preferred=%s",
            source_path.name,
            extracted_doi,
            preferred_doi,
        )

    if preferred_year and extracted_year and preferred_year != extracted_year:
        logger.warning(
            "OCR-extracted year differs from discovered year for %s: extracted=%s preferred=%s",
            source_path.name,
            extracted_year,
            preferred_year,
        )

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

    slug = entry_id.removeprefix("paper-")
    paper_dir = kb_path / "papers" / topic / slug
    paper_dir.mkdir(parents=True, exist_ok=True)

    md_path = paper_dir / "paper.md"

    # Extract embedded images from PDF (figures, charts) — best effort
    if not is_markdown and config.extract_pdf_images:
        try:
            from papermind.ingestion.glm_ocr import extract_images

            image_dir = paper_dir / "images"
            image_files = extract_images(source_path, image_dir)
            if image_files:
                markdown += "\n\n---\n\n## Figures\n\n"
                for img_name in image_files:
                    markdown += f"![{img_name}](images/{img_name})\n\n"
        except Exception:  # noqa: BLE001
            logger.debug("Image extraction skipped for %s", source_path.name)

    fm = build_frontmatter(
        type="paper",
        id=entry_id,
        title=title,
        topic=topic,
        doi=doi,
        **({"year": year} if year is not None else {}),
        **({"abstract": abstract} if abstract else {}),
        **({"cites": cites} if cites else {}),
        **({"cited_by": cited_by} if cited_by else {}),
    )

    metadata_findings = validate_paper_metadata(fm, path=str(md_path.relative_to(kb_path)))
    errors = [finding.message for finding in metadata_findings if finding.severity == "error"]
    warnings = [finding.message for finding in metadata_findings if finding.severity == "warning"]
    if errors:
        raise ValidationError("; ".join(errors))
    for warning in warnings:
        logger.warning("Paper metadata warning for %s: %s", source_path.name, warning)

    post = frontmatter.Post(markdown)
    post.metadata = fm
    md_path.write_text(frontmatter.dumps(post))

    # Copy source file into the paper directory
    import shutil

    if is_markdown:
        original_copy = paper_dir / "original.md"
    else:
        original_copy = paper_dir / "original.pdf"
    if not original_copy.exists():
        shutil.copy2(source_path, original_copy)

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
    """Ingest all PDF and markdown files in *folder* into the knowledge base.

    Walks *folder* recursively for ``*.pdf``, ``*.md``, and ``*.markdown``
    files.  Each file is processed individually; errors are logged and counted
    rather than propagated so that the remaining files are always attempted.
    A single qmd reindex is issued at the end (not once per file).

    Duplicate-DOI detection follows the same immutable policy as
    :func:`ingest_paper`: a paper whose DOI already exists in the catalog is
    silently skipped and counted as *skipped*.

    Args:
        folder: Directory to walk for paper files.
        topic: Topic category applied to every ingested paper.
        kb_path: Knowledge base root.
        config: PaperMind configuration.

    Returns:
        :class:`BatchResult` with ingested / skipped / failed counts.
    """
    result = BatchResult()

    source_paths = sorted(
        p
        for p in folder.rglob("*")
        if p.suffix.lower() in (".pdf", ".md", ".markdown") and p.is_file()
    )
    logger.info("Batch ingestion: found %d file(s) in %s", len(source_paths), folder)

    for source_path in source_paths:
        try:
            entry = ingest_paper(
                source_path,
                topic,
                kb_path,
                config,
                no_reindex=True,  # Reindex once at end of batch
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to ingest %s: %s", source_path.name, exc)
            result.failed += 1
            result.errors[source_path] = str(exc)
            continue

        if entry is None:
            logger.info("Skipped %s (duplicate).", source_path.name)
            result.skipped += 1
        else:
            logger.info("Ingested %s as %r.", source_path.name, entry.id)
            result.ingested += 1

    # Single reindex at end of batch (only if anything was actually ingested).
    if result.ingested > 0:
        from papermind.query.qmd import qmd_reindex

        qmd_reindex(kb_path)

    logger.info("Batch complete: %s", result)
    return result
