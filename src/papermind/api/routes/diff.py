"""API diff endpoint — compare package versions."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from papermind.api.deps import get_kb_path

router = APIRouter()


@router.get("/api-diff/{old_name}/{new_name}")
async def api_diff(
    old_name: str,
    new_name: str,
    function: str = Query("", description="Filter to specific function"),
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Compare two package API versions for breaking changes."""
    from papermind.api_diff import diff_apis

    try:
        result = diff_apis(kb_path, old_name, new_name, function_filter=function)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "old_name": result.old_name,
        "new_name": result.new_name,
        "old_count": result.old_count,
        "new_count": result.new_count,
        "added": [{"function": e.function, "detail": e.detail} for e in result.added],
        "removed": [
            {"function": e.function, "detail": e.detail} for e in result.removed
        ],
        "changed": [
            {"function": e.function, "detail": e.detail} for e in result.changed
        ],
    }
