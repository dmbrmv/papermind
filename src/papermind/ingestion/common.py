"""Frontmatter generation, slugification, and path utilities."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path


def slugify(text: str) -> str:
    """Convert text to URL-safe slug.

    Args:
        text: Input text to slugify.

    Returns:
        Lowercase, hyphenated slug with only alphanumeric chars.
    """
    # Normalize unicode → ASCII approximation
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text


def generate_id(
    type_: str,
    name: str,
    *,
    year: int | None = None,
    kb_path: Path | None = None,
) -> str:
    """Generate a unique ID for a catalog entry, with filesystem collision detection.

    Args:
        type_: One of "paper", "package", "codebase".
        name: Title (papers) or name (packages/codebases).
        year: Publication year (papers only).
        kb_path: Knowledge base root. If provided, checks filesystem for collisions
            and appends -2, -3, etc. to avoid them.

    Returns:
        ID string like "paper-green-and-ampt-model-1911".
    """
    slug = slugify(name)
    base_id = f"{type_}-{slug}-{year}" if year is not None else f"{type_}-{slug}"

    if kb_path is None:
        return base_id

    # Filesystem-based collision detection
    candidate = base_id
    suffix = 2
    while _id_exists_on_filesystem(candidate, kb_path):
        candidate = f"{base_id}-{suffix}"
        suffix += 1
    return candidate


def _id_exists_on_filesystem(entry_id: str, kb_path: Path) -> bool:
    """Check if an ID already maps to a file on disk.

    Searches papers/, packages/, codebases/ for markdown files whose
    frontmatter ``id`` field matches entry_id. This is authoritative —
    catalog.json may be stale.

    Args:
        entry_id: The candidate ID to look up.
        kb_path: Knowledge base root directory.

    Returns:
        True if the ID is already in use on the filesystem.
    """
    import frontmatter as fm_lib

    for subdir in ["papers", "packages", "codebases"]:
        search_dir = kb_path / subdir
        if not search_dir.exists():
            continue
        for md_file in search_dir.rglob("*.md"):
            try:
                post = fm_lib.load(md_file)
                if post.metadata.get("id") == entry_id:
                    return True
            except Exception:
                continue
    return False


def build_frontmatter(*, type: str, **kwargs: object) -> dict:  # noqa: A002
    """Build a frontmatter dict with auto-populated fields.

    Args:
        type: Document type (paper, package, codebase).
        **kwargs: Additional frontmatter fields (title, authors, year, topic, etc.).

    Returns:
        Dict suitable for YAML frontmatter serialization.
    """
    fm: dict = {"type": type}
    fm.update(kwargs)
    if "added" not in fm:
        fm["added"] = date.today().isoformat()
    return fm
