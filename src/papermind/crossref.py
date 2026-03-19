"""Cross-reference engine — keyword-based paper similarity beyond citations."""

from __future__ import annotations

import logging
from pathlib import Path

import frontmatter as fm_lib

logger = logging.getLogger(__name__)


def compute_cross_refs(
    kb_path: Path,
    *,
    min_score: float = 0.15,
    max_related: int = 5,
) -> dict[str, list[tuple[str, float]]]:
    """Compute keyword-based cross-references for all papers.

    Uses tag overlap (Jaccard similarity) between papers to find related
    work beyond the citation graph.

    Args:
        kb_path: Knowledge base root.
        min_score: Minimum Jaccard similarity to include (0-1).
        max_related: Maximum related papers per entry.

    Returns:
        Dict mapping paper ID to list of (related_id, score) tuples,
        sorted by descending score.
    """
    papers = _load_all_papers(kb_path)
    if len(papers) < 2:
        return {}

    results: dict[str, list[tuple[str, float]]] = {}

    ids = list(papers.keys())
    for i, id_a in enumerate(ids):
        tags_a = papers[id_a]["tags"]
        if not tags_a:
            continue

        scored: list[tuple[str, float]] = []
        for j, id_b in enumerate(ids):
            if i == j:
                continue
            tags_b = papers[id_b]["tags"]
            if not tags_b:
                continue

            score = _jaccard(tags_a, tags_b)
            if score >= min_score:
                scored.append((id_b, round(score, 3)))

        scored.sort(key=lambda x: -x[1])
        if scored:
            results[id_a] = scored[:max_related]

    return results


def backfill_cross_refs(
    kb_path: Path,
    *,
    min_score: float = 0.15,
    max_related: int = 5,
) -> int:
    """Compute cross-refs and write them to paper frontmatter.

    Adds/updates a ``keyword_related`` field in each paper's frontmatter
    (separate from the citation-based ``cites``/``cited_by`` fields).

    Args:
        kb_path: Knowledge base root.
        min_score: Minimum Jaccard similarity to include.
        max_related: Maximum related papers per entry.

    Returns:
        Number of papers updated.
    """
    cross_refs = compute_cross_refs(
        kb_path, min_score=min_score, max_related=max_related
    )

    updated = 0
    for paper_id, related in cross_refs.items():
        path = _find_paper_path(kb_path, paper_id)
        if not path:
            continue

        post = fm_lib.load(path)
        # Store as list of IDs (scores are ephemeral — will recompute)
        related_ids = [rid for rid, _score in related]

        if post.metadata.get("keyword_related") != related_ids:
            post.metadata["keyword_related"] = related_ids
            path.write_text(fm_lib.dumps(post))
            updated += 1
            logger.info("Updated cross-refs for %s: %d related", paper_id, len(related))

    return updated


def _load_all_papers(kb_path: Path) -> dict[str, dict]:
    """Load all papers with their tags."""
    papers: dict[str, dict] = {}
    papers_dir = kb_path / "papers"
    if not papers_dir.exists():
        return papers

    for paper_md in papers_dir.rglob("paper.md"):
        try:
            post = fm_lib.load(paper_md)
            meta = post.metadata
            if meta.get("type") != "paper":
                continue
            pid = meta.get("id", "")
            if not pid:
                continue

            tags = set(meta.get("tags", []) or [])

            # Also use topic as implicit tag
            topic = meta.get("topic", "")
            if topic:
                tags.add(topic)

            papers[pid] = {
                "tags": tags,
                "title": meta.get("title", ""),
                "path": str(paper_md.relative_to(kb_path)),
            }
        except Exception:
            continue

    return papers


def _jaccard(set_a: set, set_b: set) -> float:
    """Jaccard similarity between two tag sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _find_paper_path(kb_path: Path, paper_id: str) -> Path | None:
    """Find the filesystem path for a paper by ID."""
    papers_dir = kb_path / "papers"
    if not papers_dir.exists():
        return None

    for paper_md in papers_dir.rglob("paper.md"):
        try:
            post = fm_lib.load(paper_md)
            if post.metadata.get("id") == paper_id:
                return paper_md
        except Exception:
            continue
    return None
