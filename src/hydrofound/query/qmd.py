"""qmd subprocess wrapper — semantic search backend.

qmd is an optional hybrid search engine (BM25 + semantic embeddings).
When qmd is not installed, callers should fall back to
:func:`hydrofound.query.fallback.fallback_search`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from hydrofound.query.fallback import SearchResult


def is_qmd_available() -> bool:
    """Check if qmd is on PATH.

    Returns:
        True if the ``qmd`` binary can be found, False otherwise.
    """
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
        scope: Optional scope filter — restricts search to
            ``kb_path / scope`` when non-empty
            (e.g. ``"papers"``, ``"packages"``, ``"codebases"``).
        limit: Maximum number of results to return.

    Returns:
        List of :class:`~hydrofound.query.fallback.SearchResult` ranked
        by descending relevance score.

    Raises:
        RuntimeError: If qmd exits with a non-zero return code.
    """
    search_dir = kb_path / scope if scope else kb_path

    cmd = [
        "qmd",
        "search",
        query,
        "--dir",
        str(search_dir),
        "--limit",
        str(limit),
        "--json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(f"qmd search failed: {result.stderr}")

    data: list[dict[str, object]] = json.loads(result.stdout)
    results: list[SearchResult] = []
    for item in data:
        path_str = str(item.get("path", ""))
        results.append(
            SearchResult(
                path=path_str,
                title=str(item.get("title", Path(path_str).stem if path_str else "")),
                snippet=str(item.get("snippet", "")),
                score=float(item.get("score", 0.0)),
            )
        )
    return results


def qmd_reindex(kb_path: Path) -> None:
    """Trigger qmd to reindex the knowledge base.

    This is a best-effort operation: if qmd is not installed the call
    returns silently without raising an error.

    Args:
        kb_path: Knowledge base root directory.
    """
    if not is_qmd_available():
        return

    cmd = ["qmd", "index", str(kb_path)]
    subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
