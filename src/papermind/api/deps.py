"""FastAPI dependencies — KB path, path validation."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import HTTPException, Request

# Write lock retained as a safety net for JSON-backend KBs.
# SQLite handles concurrency natively; this is for legacy fallback.
_write_lock = asyncio.Lock()


def get_kb_path(request: Request) -> Path:
    """Extract the KB path from app state.

    Raises:
        HTTPException: If KB path is not configured.
    """
    kb_path: Path | None = request.app.state.kb_path
    if kb_path is None or not kb_path.is_dir():
        raise HTTPException(status_code=503, detail="Knowledge base not configured")
    return kb_path


def get_write_lock(request: Request) -> asyncio.Lock:
    """Return the global write lock."""
    return _write_lock


def validate_file_path(file_path: str, request: Request) -> Path:
    """Validate and resolve a file path from the request.

    Checks that the path exists and is within allowed directories.

    Args:
        file_path: Raw path string from the request.
        request: FastAPI request (for app state).

    Returns:
        Resolved Path.

    Raises:
        HTTPException: If path is invalid or outside allowed directories.
    """
    resolved = Path(file_path).resolve()

    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    # Check allowed paths
    allowed = _get_allowed_paths(request)
    if allowed and not any(resolved.is_relative_to(a) for a in allowed):
        raise HTTPException(
            status_code=403,
            detail="Path outside allowed directories",
        )

    return resolved


def _get_allowed_paths(request: Request) -> list[Path]:
    """Get allowed paths from env or app state."""
    env_paths = os.environ.get("PAPERMIND_ALLOWED_PATHS", "")
    if env_paths:
        return [Path(p).resolve() for p in env_paths.split(":") if p]

    # Default: KB path + cwd
    kb_path = getattr(request.app.state, "kb_path", None)
    paths = [Path.cwd()]
    if kb_path:
        paths.append(kb_path)
    return paths
