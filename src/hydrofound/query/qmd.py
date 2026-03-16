"""qmd subprocess wrapper — semantic search backend.

qmd is an optional hybrid search engine (BM25 + semantic embeddings + LLM reranking).
When qmd is not installed, callers should fall back to
:func:`hydrofound.query.fallback.fallback_search`.

Requires: ``npm install -g @tobilu/qmd``
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from hydrofound.query.fallback import SearchResult


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
        scope: Optional scope filter (unused in qmd v2 — searches all collections).
        limit: Maximum number of results to return.

    Returns:
        List of SearchResult ranked by descending relevance score.

    Raises:
        RuntimeError: If qmd exits with a non-zero return code.
    """
    cmd = ["qmd", "search", query, "--json"]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(kb_path))  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(f"qmd search failed: {result.stderr}")

    data: list[dict[str, object]] = json.loads(result.stdout)
    results: list[SearchResult] = []
    for item in data[:limit]:
        path_str = str(item.get("file", "") or item.get("path", ""))
        # qmd v2 returns qmd:// URIs — extract the relative path
        if "://" in path_str:
            # qmd://collection-name/papers/foo.md → papers/foo.md
            parts = path_str.split("://", 1)[-1]
            # Remove collection name prefix
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

        results.append(
            SearchResult(
                path=path_str,
                title=str(item.get("title", Path(path_str).stem if path_str else "")),
                snippet=str(item.get("snippet", "")),
                score=score,
            )
        )
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
