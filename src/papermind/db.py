"""SQLite backend — concurrent-safe storage for catalog and sessions.

Replaces catalog.json (read-modify-write) and sessions/*.json with a
single ``papermind.db`` file using WAL mode for read/write parallelism.

Markdown frontmatter remains the authoritative source for paper content.
SQLite stores only the mutable coordination layer: catalog index entries
and research session data.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


def _db_path(kb_path: Path) -> Path:
    """Return the path to papermind.db."""
    return kb_path / ".papermind" / "papermind.db"


def has_db(kb_path: Path) -> bool:
    """Check if a SQLite database exists for this KB."""
    return _db_path(kb_path).exists()


@contextmanager
def get_connection(kb_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Open a connection to the KB database with WAL mode.

    Creates the database and schema if it doesn't exist yet.

    Args:
        kb_path: Knowledge base root.

    Yields:
        sqlite3.Connection with row_factory set to sqlite3.Row.
    """
    db = _db_path(kb_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    _ensure_schema(conn)

    try:
        yield conn
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entries (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            path TEXT NOT NULL,
            title TEXT DEFAULT '',
            topic TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            added TEXT DEFAULT '',
            updated TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            doi TEXT DEFAULT '',
            files TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created TEXT NOT NULL,
            closed INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS session_entries (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            agent TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            timestamp TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_entries_type
            ON entries(type);
        CREATE INDEX IF NOT EXISTS idx_entries_topic
            ON entries(topic);
        CREATE INDEX IF NOT EXISTS idx_entries_doi
            ON entries(doi);
        CREATE INDEX IF NOT EXISTS idx_session_entries_session
            ON session_entries(session_id);
    """)


# ---------------------------------------------------------------------------
# Catalog operations
# ---------------------------------------------------------------------------


def db_add_entry(conn: sqlite3.Connection, entry: dict) -> None:
    """Insert or replace a catalog entry."""
    conn.execute(
        """INSERT OR REPLACE INTO entries
           (id, type, path, title, topic, tags, added, updated,
            source_url, doi, files)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            entry["id"],
            entry["type"],
            entry["path"],
            entry.get("title", ""),
            entry.get("topic", ""),
            json.dumps(entry.get("tags", [])),
            entry.get("added", ""),
            entry.get("updated", ""),
            entry.get("source_url", ""),
            entry.get("doi", ""),
            json.dumps(entry.get("files", [])),
        ),
    )
    conn.commit()


def db_remove_entry(conn: sqlite3.Connection, entry_id: str) -> None:
    """Remove a catalog entry by ID."""
    conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.commit()


def db_get_entry(conn: sqlite3.Connection, entry_id: str) -> dict | None:
    """Get a catalog entry by ID."""
    row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    if row is None:
        return None
    return _row_to_entry(row)


def db_get_all_entries(conn: sqlite3.Connection) -> list[dict]:
    """Get all catalog entries."""
    rows = conn.execute("SELECT * FROM entries ORDER BY id").fetchall()
    return [_row_to_entry(r) for r in rows]


def db_has_doi(conn: sqlite3.Connection, doi: str) -> bool:
    """Check if a DOI exists in the catalog."""
    row = conn.execute("SELECT 1 FROM entries WHERE doi = ? LIMIT 1", (doi,)).fetchone()
    return row is not None


def db_stats(conn: sqlite3.Connection) -> dict:
    """Get catalog statistics."""
    rows = conn.execute(
        "SELECT type, COUNT(*) as cnt FROM entries GROUP BY type"
    ).fetchall()
    type_counts = {r["type"]: r["cnt"] for r in rows}

    topic_rows = conn.execute(
        "SELECT topic, COUNT(*) as cnt FROM entries WHERE type = 'paper' GROUP BY topic"
    ).fetchall()
    topics = {r["topic"]: r["cnt"] for r in topic_rows}

    total = sum(type_counts.values())
    return {
        "papers": type_counts.get("paper", 0),
        "packages": type_counts.get("package", 0),
        "codebases": type_counts.get("codebase", 0),
        "topics": topics,
        "total": total,
    }


def _row_to_entry(row: sqlite3.Row) -> dict:
    """Convert a database row to a dict matching CatalogEntry fields."""
    return {
        "id": row["id"],
        "type": row["type"],
        "path": row["path"],
        "title": row["title"],
        "topic": row["topic"],
        "tags": json.loads(row["tags"]),
        "added": row["added"],
        "updated": row["updated"],
        "source_url": row["source_url"],
        "doi": row["doi"],
        "files": json.loads(row["files"]),
    }


# ---------------------------------------------------------------------------
# Session operations
# ---------------------------------------------------------------------------


def db_create_session(
    conn: sqlite3.Connection, session_id: str, name: str, created: str
) -> None:
    """Create a new session."""
    conn.execute(
        "INSERT INTO sessions (id, name, created) VALUES (?, ?, ?)",
        (session_id, name, created),
    )
    conn.commit()


def db_add_session_entry(
    conn: sqlite3.Connection,
    session_id: str,
    agent: str,
    content: str,
    tags: list[str],
    timestamp: str,
) -> None:
    """Add an entry to a session."""
    conn.execute(
        """INSERT INTO session_entries
           (session_id, agent, content, tags, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, agent, content, json.dumps(tags), timestamp),
    )
    conn.commit()


def db_get_session(conn: sqlite3.Connection, session_id: str) -> dict | None:
    """Get a session with its entries."""
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        return None

    entry_rows = conn.execute(
        "SELECT * FROM session_entries WHERE session_id = ? ORDER BY rowid",
        (session_id,),
    ).fetchall()

    return {
        "id": row["id"],
        "name": row["name"],
        "created": row["created"],
        "closed": bool(row["closed"]),
        "entries": [
            {
                "agent": e["agent"],
                "content": e["content"],
                "tags": json.loads(e["tags"]),
                "timestamp": e["timestamp"],
            }
            for e in entry_rows
        ],
    }


def db_close_session(conn: sqlite3.Connection, session_id: str) -> bool:
    """Close a session. Returns True if found."""
    cursor = conn.execute("UPDATE sessions SET closed = 1 WHERE id = ?", (session_id,))
    conn.commit()
    return cursor.rowcount > 0


def db_is_session_closed(conn: sqlite3.Connection, session_id: str) -> bool | None:
    """Check if a session is closed. Returns None if not found."""
    row = conn.execute(
        "SELECT closed FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        return None
    return bool(row["closed"])


def db_list_sessions(conn: sqlite3.Connection) -> list[dict]:
    """List all sessions with entry counts."""
    rows = conn.execute("""
        SELECT s.*, COUNT(e.rowid) as entry_count
        FROM sessions s
        LEFT JOIN session_entries e ON s.id = e.session_id
        GROUP BY s.id
        ORDER BY s.created DESC
    """).fetchall()

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "created": r["created"],
            "closed": bool(r["closed"]),
            "entry_count": r["entry_count"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def migrate_json_to_db(kb_path: Path) -> dict:
    """Migrate existing JSON files to SQLite.

    Imports catalog.json and sessions/*.json into papermind.db.
    Does NOT delete old files — they become backups.

    Args:
        kb_path: Knowledge base root.

    Returns:
        Dict with migration stats: entries_migrated, sessions_migrated.
    """
    stats = {"entries_migrated": 0, "sessions_migrated": 0}

    with get_connection(kb_path) as conn:
        # Migrate catalog.json
        catalog_path = kb_path / "catalog.json"
        if catalog_path.exists():
            data = json.loads(catalog_path.read_text())
            for entry in data:
                db_add_entry(conn, entry)
                stats["entries_migrated"] += 1

        # Migrate sessions
        sessions_dir = kb_path / ".papermind" / "sessions"
        if sessions_dir.exists():
            for session_file in sessions_dir.glob("*.json"):
                try:
                    sdata = json.loads(session_file.read_text())
                    db_create_session(
                        conn,
                        sdata["id"],
                        sdata["name"],
                        sdata["created"],
                    )
                    if sdata.get("closed"):
                        db_close_session(conn, sdata["id"])
                    for entry in sdata.get("entries", []):
                        db_add_session_entry(
                            conn,
                            sdata["id"],
                            entry["agent"],
                            entry["content"],
                            entry.get("tags", []),
                            entry["timestamp"],
                        )
                    stats["sessions_migrated"] += 1
                except Exception:
                    continue

    return stats
