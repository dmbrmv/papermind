"""KB sharing — export and import portable archives.

Export creates a ``.pmkb`` file (zip) containing selected papers/packages
with their markdown, frontmatter, and originals.  Import merges an archive
into an existing KB with DOI/title dedup.
"""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def export_kb(
    kb_path: Path,
    output_path: Path,
    *,
    topic: str = "",
    entry_type: str = "",
) -> dict:
    """Export KB entries to a .pmkb archive.

    Args:
        kb_path: Knowledge base root.
        output_path: Path for the output .pmkb file.
        topic: If provided, only export papers in this topic.
        entry_type: If provided, only export this type (paper/package/codebase).

    Returns:
        Dict with export stats: entries, files, bytes.
    """
    from papermind.catalog.index import CatalogIndex

    catalog = CatalogIndex(kb_path)
    entries = catalog.entries

    if topic:
        entries = [e for e in entries if e.topic == topic]
    if entry_type:
        entries = [e for e in entries if e.type == entry_type]

    if not entries:
        return {"entries": 0, "files": 0, "bytes": 0}

    file_count = 0
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Write catalog subset
        catalog_data = [e.to_dict() for e in entries]
        zf.writestr("catalog.json", json.dumps(catalog_data, indent=2))
        file_count += 1

        # Write each entry's files
        for entry in entries:
            entry_path = kb_path / entry.path
            if not entry_path.exists():
                continue

            # Add the main file
            rel = entry.path
            zf.write(entry_path, rel)
            file_count += 1

            # Add sibling files (original.pdf, original.md, images/)
            parent = entry_path.parent
            for sibling in parent.rglob("*"):
                if sibling.is_file() and sibling != entry_path:
                    sib_rel = str(sibling.relative_to(kb_path))
                    zf.write(sibling, sib_rel)
                    file_count += 1

    size = output_path.stat().st_size
    return {"entries": len(entries), "files": file_count, "bytes": size}


def import_kb(
    kb_path: Path,
    archive_path: Path,
    *,
    merge: bool = True,
) -> dict:
    """Import a .pmkb archive into an existing KB.

    Args:
        kb_path: Knowledge base root.
        archive_path: Path to the .pmkb archive.
        merge: If True, skip entries with duplicate DOI/title.
            If False, overwrite existing entries.

    Returns:
        Dict with import stats: imported, skipped, files.
    """
    from papermind.catalog.index import CatalogEntry, CatalogIndex

    catalog = CatalogIndex(kb_path)
    existing_dois = {e.doi for e in catalog.entries if e.doi}
    existing_titles = {e.title.lower() for e in catalog.entries if e.title}

    stats = {"imported": 0, "skipped": 0, "files": 0}

    with zipfile.ZipFile(archive_path, "r") as zf:
        # Read the archive's catalog
        try:
            archive_catalog = json.loads(zf.read("catalog.json"))
        except (KeyError, json.JSONDecodeError):
            logger.error("Invalid archive: missing or corrupt catalog.json")
            return stats

        for entry_data in archive_catalog:
            entry_id = entry_data.get("id", "")
            doi = entry_data.get("doi", "")
            title = entry_data.get("title", "")

            # Dedup check
            if merge:
                if doi and doi in existing_dois:
                    logger.info("Skipping %s (duplicate DOI)", entry_id)
                    stats["skipped"] += 1
                    continue
                if title and title.lower() in existing_titles:
                    logger.info("Skipping %s (duplicate title)", entry_id)
                    stats["skipped"] += 1
                    continue

            # Extract files for this entry
            entry_path = entry_data.get("path", "")
            if not entry_path:
                continue

            # Find all files belonging to this entry in the archive
            entry_dir = str(Path(entry_path).parent)
            for zinfo in zf.infolist():
                if zinfo.filename == "catalog.json":
                    continue
                if zinfo.filename.startswith(entry_dir):
                    target = kb_path / zinfo.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(zinfo.filename))
                    stats["files"] += 1

            # Add to catalog
            from dataclasses import fields

            known = {f.name for f in fields(CatalogEntry)}
            filtered = {k: v for k, v in entry_data.items() if k in known}
            catalog.add(CatalogEntry(**filtered))
            stats["imported"] += 1

            # Track for dedup in this batch
            if doi:
                existing_dois.add(doi)
            if title:
                existing_titles.add(title.lower())

    # Regenerate catalog.md
    from papermind.catalog.render import render_catalog_md

    (kb_path / "catalog.md").write_text(render_catalog_md(catalog.entries))

    return stats
