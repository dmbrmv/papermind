"""Search endpoints — scan, summary, detail, discover."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from papermind.api.deps import get_kb_path

router = APIRouter()


@router.get("/search/scan")
async def scan(
    q: str = Query(..., description="Search query"),
    scope: str = Query("", description="papers, packages, or codebases"),
    topic: str = Query("", description="Filter by topic"),
    year_from: int | None = Query(None, description="Papers from this year onward"),
    limit: int = Query(20, ge=1, le=100),
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Fast triage search — titles, IDs, scores (~50 tokens/result)."""
    results = await asyncio.to_thread(
        _search, kb_path, q, scope, topic, year_from, limit
    )

    # Enrich search results with catalog metadata (paper titles, IDs)
    from papermind.catalog.index import CatalogIndex

    catalog = CatalogIndex(kb_path)
    path_to_entry = {e.path: e for e in catalog.entries}

    enriched = []
    for i, r in enumerate(results, 1):
        entry = path_to_entry.get(r.path)
        enriched.append(
            {
                "rank": i,
                "score": r.score,
                "title": entry.title if entry else r.title,
                "path": r.path,
                "id": entry.id if entry else "",
                "topic": entry.topic if entry else "",
                "doi": entry.doi if entry else "",
            }
        )

    return {"query": q, "count": len(enriched), "results": enriched}


@router.get("/search/summary")
async def summary(
    q: str = Query(...),
    scope: str = Query(""),
    topic: str = Query(""),
    limit: int = Query(5, ge=1, le=50),
    budget: int = Query(0, description="Max output tokens (approximate)"),
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Structured summaries — title, abstract, metadata (~500 tokens/result)."""
    import frontmatter as fm_lib

    results = await asyncio.to_thread(_search, kb_path, q, scope, topic, None, limit)
    summaries = []
    total_chars = 0

    for r in results:
        full_path = kb_path / r.path
        meta: dict = {}
        if full_path.exists():
            try:
                post = fm_lib.load(full_path)
                meta = dict(post.metadata)
            except Exception:
                pass

        entry = {
            "title": r.title,
            "path": r.path,
            "doi": meta.get("doi", ""),
            "year": meta.get("year"),
            "topic": meta.get("topic", ""),
            "abstract": (meta.get("abstract", "") or "")[:300],
            "snippet": r.snippet[:200] if r.snippet else "",
        }

        block_len = sum(len(str(v)) for v in entry.values())
        if budget and total_chars + block_len > budget * 4:
            break
        summaries.append(entry)
        total_chars += block_len

    return {"query": q, "count": len(summaries), "results": summaries}


@router.get("/search/detail/{path:path}")
async def detail(
    path: str,
    budget: int = Query(0),
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Full document read — complete text."""
    full_path = (kb_path / path).resolve()
    if not full_path.is_relative_to(kb_path.resolve()):
        raise HTTPException(status_code=403, detail="Path outside KB")
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    content = await asyncio.to_thread(full_path.read_text)
    if budget:
        max_chars = budget * 4
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[...truncated to budget...]"

    return {"path": path, "content": content}


@router.get("/search/discover")
async def discover(
    query: str = Query(...),
    limit: int = Query(10, ge=1, le=50),
    source: str = Query("all", description="all, semantic_scholar, or exa"),
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Search academic APIs for papers (OpenAlex, Semantic Scholar, Exa)."""
    from papermind.config import load_config
    from papermind.discovery.orchestrator import discover_papers
    from papermind.discovery.providers import build_providers

    config = load_config(kb_path)
    providers = build_providers(source, config)
    if not providers:
        raise HTTPException(status_code=503, detail="No search providers configured")

    results = await discover_papers(query, providers, limit=limit)
    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "title": r.title,
                "year": r.year,
                "doi": r.doi or "",
                "abstract": (r.abstract or "")[:300],
                "is_open_access": r.is_open_access,
                "pdf_url": r.pdf_url or "",
            }
            for r in results
        ],
    }


def _search(
    kb_path: Path,
    q: str,
    scope: str,
    topic: str,
    year_from: int | None,
    limit: int,
) -> list:
    """Run search (thread-safe, called via to_thread)."""
    from papermind.query.dispatch import run_search

    return run_search(
        kb_path,
        q,
        scope=scope,
        topic=topic,
        year_from=year_from,
        limit=limit,
    )
