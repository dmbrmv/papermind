"""qmd subprocess wrapper — semantic search backend.

qmd is an optional hybrid search engine (BM25 + semantic embeddings + LLM reranking).
When qmd is not installed, callers should fall back to
:func:`papermind.query.fallback.fallback_search`.

Requires: ``npm install -g @tobilu/qmd``
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from papermind.query.fallback import SearchResult


def is_qmd_available() -> bool:
    """Check if qmd is on PATH."""
    return shutil.which("qmd") is not None


def qmd_search(
    kb_path: Path,
    query: str,
    *,
    scope: str = "",
    limit: int = 10,
) -> list[SearchResult]:
    """Search the knowledge base using qmd.

    Args:
        kb_path: Knowledge base root directory.
        query: Search query string.
        scope: Optional path-prefix filter (e.g. ``"papers"``). Results whose
            collection-relative path does not start with it are dropped.
        limit: Maximum number of distinct papers to return.

    Returns:
        List of SearchResult ranked by descending relevance score, de-duplicated
        to one entry per paper (see body — qmd indexes paper.md + original.md).

    Raises:
        RuntimeError: If qmd exits with a non-zero return code.
    """
    # qmd's -n caps output (default 20 for --json). Every paper is indexed as
    # BOTH paper.md and a near-duplicate original.md sibling, so over-fetch ~2x
    # the limit to leave enough DISTINCT papers after de-duplication below.
    n_fetch = max(limit * 2, 20)
    cmd = ["qmd", "search", query, "--json", "-n", str(n_fetch)]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(kb_path))  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(f"qmd search failed: {result.stderr}")

    data: list[dict[str, object]] = json.loads(result.stdout)

    # Collapse the paper.md + original.md siblings qmd indexes for every paper
    # (both match **/*.md) to one hit per papers/<id>/ directory, preferring
    # paper.md — it carries the clean decoded title/H1 while original.md keeps
    # the raw encoded one. De-dups RESULTS only; the index still holds both
    # files, so on-disk size and query speed are unchanged. Scan the full
    # result set so a later paper.md can upgrade an earlier original.md hit,
    # then truncate to `limit`.
    results: list[SearchResult] = []
    dir_to_idx: dict[str, int] = {}
    for item in data:
        path_str = str(item.get("file", "") or item.get("path", ""))
        # qmd v2 returns qmd:// URIs — extract the collection-relative path
        if "://" in path_str:
            # qmd://collection-name/papers/foo.md → papers/foo.md
            parts = path_str.split("://", 1)[-1]
            slash_idx = parts.find("/")
            if slash_idx >= 0:
                path_str = parts[slash_idx + 1 :]

        # Strip line number suffix (e.g. papers/foo.md:19)
        if ":" in path_str:
            path_str = path_str.rsplit(":", 1)[0]

        # Filter by scope if requested
        if scope and not path_str.startswith(scope):
            continue

        score = float(item.get("score", 0.0))
        # qmd returns 0-100 percentage, normalize to 0-1 range
        if score > 1:
            score = score / 100.0

        path = Path(path_str)
        candidate = SearchResult(
            path=path_str,
            title=str(item.get("title", path.stem if path_str else "")),
            snippet=str(item.get("snippet", "")),
            score=score,
        )

        # Only the paper.md/original.md pair shares a dedup key; every other
        # file keys by its own path so unrelated same-folder files (e.g. root
        # catalog.md/README.md) are never collapsed together.
        if path.name in ("paper.md", "original.md"):
            dir_key = str(path.parent)
        else:
            dir_key = path_str

        if dir_key in dir_to_idx:
            kept_idx = dir_to_idx[dir_key]
            kept = results[kept_idx]
            # Upgrade original.md → paper.md, keeping the better score.
            if path.name == "paper.md" and Path(kept.path).name != "paper.md":
                results[kept_idx] = SearchResult(
                    path=candidate.path,
                    title=candidate.title,
                    snippet=candidate.snippet,
                    score=max(kept.score, candidate.score),
                )
            continue

        if len(results) >= limit:
            # Have enough distinct papers; keep scanning only to upgrade ones
            # already collected, never to add new results.
            continue

        dir_to_idx[dir_key] = len(results)
        results.append(candidate)

    return results


def qmd_reindex(kb_path: Path) -> None:
    """Trigger qmd to reindex the knowledge base.

    Best-effort: returns silently if qmd is not installed.

    Args:
        kb_path: Knowledge base root directory.
    """
    if not is_qmd_available():
        return

    # qmd v2 reindexes all collections automatically
    subprocess.run(
        ["qmd", "collection", "refresh"],
        capture_output=True,
        text=True,
        check=False,
    )  # noqa: S603
