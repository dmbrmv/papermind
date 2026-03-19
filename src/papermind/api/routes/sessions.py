"""Session endpoints — create, add, read, list, close."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from papermind.api.deps import get_kb_path, get_write_lock
from papermind.api.schemas import SessionAddRequest, SessionCreateRequest

router = APIRouter()


@router.post("/sessions")
async def create_session(
    body: SessionCreateRequest,
    kb_path: Path = Depends(get_kb_path),
    lock: asyncio.Lock = Depends(get_write_lock),
) -> dict:
    """Create a new research session."""
    from papermind.session import create_session as _create

    async with lock:
        try:
            session = await asyncio.to_thread(_create, kb_path, body.name)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {"id": session.id, "name": session.name, "created": session.created}


@router.post("/sessions/{session_id}/entries")
async def add_entry(
    session_id: str,
    body: SessionAddRequest,
    kb_path: Path = Depends(get_kb_path),
    lock: asyncio.Lock = Depends(get_write_lock),
) -> dict:
    """Add an entry to a session."""
    from papermind.session import add_to_session

    async with lock:
        try:
            entry = await asyncio.to_thread(
                add_to_session,
                kb_path,
                session_id,
                body.content,
                agent=body.agent,
                tags=body.tags or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"agent": entry.agent, "timestamp": entry.timestamp}


@router.get("/sessions/{session_id}")
async def read_session(
    session_id: str,
    tag: str = "",
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Read a session's accumulated findings."""
    from papermind.session import read_session as _read

    session = _read(kb_path, session_id, tag=tag)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return {
        "id": session.id,
        "name": session.name,
        "created": session.created,
        "closed": session.closed,
        "entries": [
            {
                "agent": e.agent,
                "content": e.content,
                "tags": e.tags,
                "timestamp": e.timestamp,
            }
            for e in session.entries
        ],
    }


@router.post("/sessions/{session_id}/close")
async def close_session(
    session_id: str,
    kb_path: Path = Depends(get_kb_path),
    lock: asyncio.Lock = Depends(get_write_lock),
) -> dict:
    """Close a session (no more entries can be added)."""
    from papermind.session import close_session as _close

    async with lock:
        session = await asyncio.to_thread(_close, kb_path, session_id)

    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return {"id": session.id, "closed": True}


@router.get("/sessions")
async def list_sessions(
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """List all sessions."""
    from papermind.session import list_sessions as _list

    sessions = _list(kb_path)
    return {
        "count": len(sessions),
        "sessions": [
            {
                "id": s.id,
                "name": s.name,
                "created": s.created,
                "closed": s.closed,
                "entry_count": len(s.entries),
            }
            for s in sessions
        ],
    }
