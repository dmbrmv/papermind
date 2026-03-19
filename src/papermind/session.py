"""Research sessions — shared scratchpad for multi-agent workflows.

A session is a named, append-only log where multiple agents (or a single
agent across turns) accumulate research findings.  The lead agent creates
a session, sub-agents contribute entries, and any agent can read the
accumulated results.

Sessions are stored as JSON files in ``.papermind/sessions/``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SessionEntry:
    """A single contribution to a research session."""

    agent: str
    """Name or identifier of the contributing agent."""
    content: str
    """The finding / note / result."""
    tags: list[str] = field(default_factory=list)
    """Optional tags for filtering."""
    timestamp: str = ""
    """ISO timestamp (auto-filled if empty)."""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


@dataclass
class Session:
    """A research session with accumulated entries."""

    id: str
    """Session identifier (slug)."""
    name: str
    """Human-readable session name."""
    created: str
    """ISO timestamp of creation."""
    closed: bool = False
    """Whether the session has been closed."""
    entries: list[SessionEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize for JSON storage."""
        return {
            "id": self.id,
            "name": self.name,
            "created": self.created,
            "closed": self.closed,
            "entries": [asdict(e) for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        """Deserialize from JSON."""
        entries = [SessionEntry(**e) for e in data.get("entries", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            created=data["created"],
            closed=data.get("closed", False),
            entries=entries,
        )


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _sessions_dir(kb_path: Path) -> Path:
    """Return (and create) the sessions directory."""
    d = kb_path / ".papermind" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_path(kb_path: Path, session_id: str) -> Path:
    """Return the file path for a session."""
    return _sessions_dir(kb_path) / f"{session_id}.json"


def _save_session(kb_path: Path, session: Session) -> None:
    """Atomically write a session to disk."""
    path = _session_path(kb_path, session.id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(session.to_dict(), indent=2))
    tmp.rename(path)


def _load_session(kb_path: Path, session_id: str) -> Session | None:
    """Load a session from disk, or None if not found."""
    path = _session_path(kb_path, session_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return Session.from_dict(data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_session(
    kb_path: Path,
    name: str,
    *,
    session_id: str = "",
) -> Session:
    """Create a new research session.

    Args:
        kb_path: Knowledge base root.
        name: Human-readable session name.
        session_id: Optional custom ID (auto-generated from name if empty).

    Returns:
        The created Session.

    Raises:
        ValueError: If a session with this ID already exists.
    """
    from papermind.ingestion.common import slugify

    sid = session_id or slugify(name)
    if _load_session(kb_path, sid) is not None:
        raise ValueError(f"Session '{sid}' already exists")

    session = Session(
        id=sid,
        name=name,
        created=datetime.now(UTC).isoformat(),
    )
    _save_session(kb_path, session)
    logger.info("Created session: %s (%s)", name, sid)
    return session


def add_to_session(
    kb_path: Path,
    session_id: str,
    content: str,
    *,
    agent: str = "user",
    tags: list[str] | None = None,
) -> SessionEntry:
    """Add an entry to an existing session.

    Args:
        kb_path: Knowledge base root.
        session_id: Session ID.
        content: The finding / note / result.
        agent: Name of the contributing agent.
        tags: Optional tags.

    Returns:
        The created SessionEntry.

    Raises:
        ValueError: If session not found or is closed.
    """
    session = _load_session(kb_path, session_id)
    if session is None:
        raise ValueError(f"Session '{session_id}' not found")
    if session.closed:
        raise ValueError(f"Session '{session_id}' is closed")

    entry = SessionEntry(
        agent=agent,
        content=content,
        tags=tags or [],
    )
    session.entries.append(entry)
    _save_session(kb_path, session)
    return entry


def read_session(
    kb_path: Path,
    session_id: str,
    *,
    tag: str = "",
) -> Session | None:
    """Read a session, optionally filtering entries by tag.

    Args:
        kb_path: Knowledge base root.
        session_id: Session ID.
        tag: If provided, only return entries with this tag.

    Returns:
        Session with (optionally filtered) entries, or None if not found.
    """
    session = _load_session(kb_path, session_id)
    if session is None or not tag:
        return session

    # Filter entries by tag
    filtered = Session(
        id=session.id,
        name=session.name,
        created=session.created,
        closed=session.closed,
        entries=[e for e in session.entries if tag in e.tags],
    )
    return filtered


def close_session(kb_path: Path, session_id: str) -> Session | None:
    """Close a session (no more entries can be added).

    Args:
        kb_path: Knowledge base root.
        session_id: Session ID.

    Returns:
        The closed Session, or None if not found.
    """
    session = _load_session(kb_path, session_id)
    if session is None:
        return None
    session.closed = True
    _save_session(kb_path, session)
    return session


def list_sessions(kb_path: Path) -> list[Session]:
    """List all sessions in the KB.

    Args:
        kb_path: Knowledge base root.

    Returns:
        List of Session objects (entries not loaded — only metadata).
    """
    sessions_dir = _sessions_dir(kb_path)
    sessions: list[Session] = []
    for path in sorted(sessions_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            s = Session.from_dict(data)
            sessions.append(s)
        except Exception:
            continue
    return sessions


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_session(session: Session) -> str:
    """Format a session as readable markdown."""
    status = "CLOSED" if session.closed else "OPEN"
    lines = [
        f"## Session: {session.name} [{status}]\n",
        f"**ID:** {session.id}",
        f"**Created:** {session.created}",
        f"**Entries:** {len(session.entries)}\n",
    ]

    for i, entry in enumerate(session.entries, 1):
        tag_str = f" [{', '.join(entry.tags)}]" if entry.tags else ""
        lines.append(f"### Entry {i} — {entry.agent}{tag_str}")
        lines.append(f"*{entry.timestamp}*\n")
        lines.append(entry.content)
        lines.append("")

    return "\n".join(lines)


def format_session_list(sessions: list[Session]) -> str:
    """Format a session list as a table."""
    if not sessions:
        return "No sessions found."

    lines = [f"**{len(sessions)} session(s):**\n"]
    for s in sessions:
        status = "closed" if s.closed else "open"
        lines.append(f"- **{s.name}** (`{s.id}`) — {len(s.entries)} entries, {status}")

    return "\n".join(lines)
