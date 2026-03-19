"""Tests for SQLite backend."""

from __future__ import annotations

import json
from pathlib import Path

from papermind.catalog.index import CatalogEntry, CatalogIndex
from papermind.db import (
    db_add_entry,
    db_add_session_entry,
    db_close_session,
    db_create_session,
    db_get_all_entries,
    db_get_entry,
    db_get_session,
    db_has_doi,
    db_list_sessions,
    db_remove_entry,
    db_stats,
    get_connection,
    has_db,
    migrate_json_to_db,
)


def _make_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")
    return kb


def _init_db(kb_path: Path) -> None:
    """Create an empty database."""
    with get_connection(kb_path):
        pass  # schema created on connect


class TestDBCatalog:
    def test_add_and_get(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        _init_db(kb)
        with get_connection(kb) as conn:
            db_add_entry(
                conn,
                {
                    "id": "paper-test",
                    "type": "paper",
                    "path": "papers/test/paper.md",
                    "title": "Test Paper",
                    "doi": "10.1234/test",
                },
            )
            entry = db_get_entry(conn, "paper-test")
        assert entry is not None
        assert entry["title"] == "Test Paper"

    def test_remove(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        _init_db(kb)
        with get_connection(kb) as conn:
            db_add_entry(
                conn,
                {
                    "id": "paper-rm",
                    "type": "paper",
                    "path": "p.md",
                },
            )
            db_remove_entry(conn, "paper-rm")
            assert db_get_entry(conn, "paper-rm") is None

    def test_has_doi(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        _init_db(kb)
        with get_connection(kb) as conn:
            db_add_entry(
                conn,
                {
                    "id": "p1",
                    "type": "paper",
                    "path": "p.md",
                    "doi": "10.9999/exists",
                },
            )
            assert db_has_doi(conn, "10.9999/exists") is True
            assert db_has_doi(conn, "10.9999/nope") is False

    def test_stats(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        _init_db(kb)
        with get_connection(kb) as conn:
            db_add_entry(
                conn,
                {
                    "id": "p1",
                    "type": "paper",
                    "path": "p.md",
                    "topic": "hydrology",
                },
            )
            db_add_entry(
                conn,
                {
                    "id": "pkg1",
                    "type": "package",
                    "path": "pkg.md",
                },
            )
            stats = db_stats(conn)
        assert stats["papers"] == 1
        assert stats["packages"] == 1
        assert stats["topics"]["hydrology"] == 1

    def test_get_all(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        _init_db(kb)
        with get_connection(kb) as conn:
            db_add_entry(
                conn,
                {
                    "id": "a",
                    "type": "paper",
                    "path": "a.md",
                },
            )
            db_add_entry(
                conn,
                {
                    "id": "b",
                    "type": "paper",
                    "path": "b.md",
                },
            )
            entries = db_get_all_entries(conn)
        assert len(entries) == 2


class TestDBSessions:
    def test_create_and_read(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        _init_db(kb)
        with get_connection(kb) as conn:
            db_create_session(conn, "test", "Test Session", "2026-01-01")
            db_add_session_entry(
                conn, "test", "agent-1", "Found paper", ["key"], "2026-01-01T00:00:00"
            )
            session = db_get_session(conn, "test")
        assert session is not None
        assert session["name"] == "Test Session"
        assert len(session["entries"]) == 1

    def test_close(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        _init_db(kb)
        with get_connection(kb) as conn:
            db_create_session(conn, "s1", "Session 1", "2026-01-01")
            db_close_session(conn, "s1")
            session = db_get_session(conn, "s1")
        assert session["closed"] is True

    def test_list(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        _init_db(kb)
        with get_connection(kb) as conn:
            db_create_session(conn, "a", "A", "2026-01-01")
            db_create_session(conn, "b", "B", "2026-01-02")
            sessions = db_list_sessions(conn)
        assert len(sessions) == 2


class TestMigration:
    def test_migrate_catalog(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        # Write JSON catalog
        (kb / "catalog.json").write_text(
            json.dumps(
                [
                    {"id": "p1", "type": "paper", "path": "p.md", "title": "Paper 1"},
                    {"id": "p2", "type": "paper", "path": "q.md", "doi": "10.1/x"},
                ]
            )
        )
        stats = migrate_json_to_db(kb)
        assert stats["entries_migrated"] == 2
        assert has_db(kb)

        # Verify entries in DB
        with get_connection(kb) as conn:
            entries = db_get_all_entries(conn)
        assert len(entries) == 2

    def test_migrate_sessions(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        sessions_dir = kb / ".papermind" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "test.json").write_text(
            json.dumps(
                {
                    "id": "test",
                    "name": "Test",
                    "created": "2026-01-01",
                    "closed": False,
                    "entries": [
                        {
                            "agent": "user",
                            "content": "Finding 1",
                            "tags": [],
                            "timestamp": "2026-01-01T00:00:00",
                        }
                    ],
                }
            )
        )
        stats = migrate_json_to_db(kb)
        assert stats["sessions_migrated"] == 1

        with get_connection(kb) as conn:
            session = db_get_session(conn, "test")
        assert session is not None
        assert len(session["entries"]) == 1


class TestCatalogIndexWithDB:
    """Test CatalogIndex uses SQLite when DB exists."""

    def test_catalog_uses_db(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        _init_db(kb)
        with get_connection(kb) as conn:
            db_add_entry(
                conn,
                {
                    "id": "p1",
                    "type": "paper",
                    "path": "p.md",
                    "title": "DB Paper",
                },
            )
        catalog = CatalogIndex(kb)
        assert catalog._use_db is True
        assert len(catalog.entries) == 1
        assert catalog.entries[0].title == "DB Paper"

    def test_catalog_add_via_db(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        _init_db(kb)
        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="new-paper",
                type="paper",
                path="new.md",
                title="New Paper",
            )
        )
        # Verify in DB
        with get_connection(kb) as conn:
            entry = db_get_entry(conn, "new-paper")
        assert entry is not None
        assert entry["title"] == "New Paper"

    def test_catalog_json_still_written(self, tmp_path: Path) -> None:
        """catalog.json is still written for backward compatibility."""
        kb = _make_kb(tmp_path)
        _init_db(kb)
        catalog = CatalogIndex(kb)
        catalog.add(
            CatalogEntry(
                id="p1",
                type="paper",
                path="p.md",
                title="Test",
            )
        )
        json_data = json.loads((kb / "catalog.json").read_text())
        assert len(json_data) == 1
