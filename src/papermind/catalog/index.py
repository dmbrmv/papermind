"""Catalog index — CRUD operations on catalog.json with atomic writes."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class CatalogEntry:
    """Single entry in the catalog."""

    id: str
    type: str  # "paper", "package", "codebase"
    path: str
    title: str = ""
    topic: str = ""
    tags: list[str] = field(default_factory=list)
    added: str = ""
    updated: str = ""
    source_url: str = ""
    doi: str = ""
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dict, omitting None and empty-string fields."""
        return {k: v for k, v in asdict(self).items() if v is not None and v != ""}


class CatalogIndex:
    """CRUD interface for catalog.json.

    catalog.json is a derived cache — frontmatter in .md files is authoritative.
    This class manages the cache with atomic writes to prevent corruption.
    """

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self._path = base_path / "catalog.json"
        self.entries: list[CatalogEntry] = self._load()

    def _load(self) -> list[CatalogEntry]:
        """Load entries from catalog.json."""
        if not self._path.exists():
            return []
        data = json.loads(self._path.read_text())
        # Filter to known fields for forward compatibility
        known_fields = {f.name for f in fields(CatalogEntry)}
        return [
            CatalogEntry(**{k: v for k, v in entry.items() if k in known_fields})
            for entry in data
        ]

    def _save(self) -> None:
        """Atomically write catalog.json (write to temp, rename)."""
        data = [e.to_dict() for e in self.entries]
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"

        # Atomic write: temp file in same dir, then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=self.base_path, prefix=".catalog-", suffix=".json"
        )
        try:
            with open(fd, "w") as f:
                f.write(content)
            Path(tmp_path).replace(self._path)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def add(self, entry: CatalogEntry) -> None:
        """Add an entry and persist to disk."""
        self.entries.append(entry)
        self._save()

    def remove(self, entry_id: str) -> bool:
        """Remove an entry by ID. Returns True if found and removed."""
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.id != entry_id]
        if len(self.entries) < before:
            self._save()
            return True
        return False

    def get(self, entry_id: str) -> CatalogEntry | None:
        """Get an entry by ID."""
        for e in self.entries:
            if e.id == entry_id:
                return e
        return None

    def has_doi(self, doi: str) -> bool:
        """Check if a DOI already exists in the catalog."""
        return any(e.doi == doi for e in self.entries)

    def stats(self) -> dict:
        """Compute summary statistics."""
        type_keys = {"paper": "papers", "package": "packages", "codebase": "codebases"}
        result: dict = {"papers": 0, "packages": 0, "codebases": 0, "topics": {}}
        for e in self.entries:
            key = type_keys.get(e.type)
            if key:
                result[key] += 1
            if e.topic:
                result["topics"][e.topic] = result["topics"].get(e.topic, 0) + 1
        return result

    @classmethod
    def rebuild(cls, base_path: Path) -> CatalogIndex:
        """Rebuild catalog from .md frontmatter (filesystem is truth)."""
        import frontmatter

        entries = []
        for md_file in base_path.rglob("*.md"):
            if md_file.name.startswith(".") or ".papermind" in md_file.parts:
                continue
            try:
                post = frontmatter.load(md_file)
                if "type" in post.metadata:
                    rel_path = str(md_file.relative_to(base_path))
                    # Discover sibling .md files in the same directory
                    sibling_files = []
                    parent_dir = md_file.parent
                    for sibling in sorted(parent_dir.glob("*.md")):
                        sibling_files.append(str(sibling.relative_to(base_path)))
                    # Derive ID: frontmatter id if present, else type+name
                    entry_type = post.metadata["type"]
                    entry_id = post.metadata.get("id", "")
                    if not entry_id:
                        entry_name = (
                            post.metadata.get("name", "") or md_file.parent.name
                        )
                        entry_id = f"{entry_type}-{entry_name}"
                    entry = CatalogEntry(
                        id=entry_id,
                        type=entry_type,
                        path=rel_path,
                        title=post.metadata.get("title", "")
                        or post.metadata.get("name", ""),
                        topic=post.metadata.get("topic", ""),
                        tags=post.metadata.get("tags", []),
                        added=post.metadata.get("added", ""),
                        updated=post.metadata.get("updated", ""),
                        doi=post.metadata.get("doi", ""),
                        files=sibling_files,
                    )
                    entries.append(entry)
            except Exception:
                continue  # skip unparseable files
        idx = cls.__new__(cls)
        idx.base_path = base_path
        idx._path = base_path / "catalog.json"
        idx.entries = entries
        idx._save()
        return idx
