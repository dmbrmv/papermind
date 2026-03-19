"""Catalog endpoints — papers, packages, codebases, stats, topics."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from papermind.api.deps import get_kb_path

router = APIRouter()


@router.get("/papers")
async def list_papers(
    topic: str = "",
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """List all papers in the KB, optionally filtered by topic."""
    from papermind.catalog.index import CatalogIndex

    catalog = CatalogIndex(kb_path)
    entries = [e for e in catalog.entries if e.type == "paper"]
    if topic:
        entries = [e for e in entries if e.topic == topic]

    return {
        "count": len(entries),
        "papers": [
            {
                "id": e.id,
                "title": e.title,
                "topic": e.topic,
                "doi": e.doi,
                "path": e.path,
                "tags": e.tags,
                "added": e.added,
            }
            for e in entries
        ],
    }


@router.get("/papers/{paper_id}")
async def get_paper(
    paper_id: str,
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Get a single paper by ID."""
    from papermind.catalog.index import CatalogIndex

    catalog = CatalogIndex(kb_path)
    entry = catalog.get(paper_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Paper not found: {paper_id}")

    # Read frontmatter for full metadata
    full_path = kb_path / entry.path
    meta: dict = {}
    content = ""
    if full_path.exists():
        import frontmatter as fm_lib

        post = fm_lib.load(full_path)
        meta = dict(post.metadata)
        content = post.content

    return {
        "id": entry.id,
        "title": entry.title,
        "topic": entry.topic,
        "doi": entry.doi,
        "path": entry.path,
        "tags": entry.tags,
        "added": entry.added,
        "year": meta.get("year"),
        "abstract": meta.get("abstract", ""),
        "equations": meta.get("equations", []),
        "cites": meta.get("cites", []),
        "cited_by": meta.get("cited_by", []),
        "content": content[:5000],
    }


@router.get("/packages")
async def list_packages(
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """List all packages in the KB."""
    from papermind.catalog.index import CatalogIndex

    catalog = CatalogIndex(kb_path)
    entries = [e for e in catalog.entries if e.type == "package"]
    return {
        "count": len(entries),
        "packages": [
            {"id": e.id, "title": e.title, "path": e.path, "files": e.files}
            for e in entries
        ],
    }


@router.get("/stats")
async def catalog_stats(
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Knowledge base statistics."""
    from papermind.catalog.index import CatalogIndex

    return CatalogIndex(kb_path).stats()


@router.get("/topics")
async def list_topics(
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Available topics in the KB."""
    from papermind.catalog.index import CatalogIndex

    stats = CatalogIndex(kb_path).stats()
    return {"topics": list(stats.get("topics", {}).keys())}
