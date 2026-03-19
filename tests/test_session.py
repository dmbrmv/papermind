"""Tests for research sessions."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from papermind.cli.main import app
from papermind.session import (
    add_to_session,
    close_session,
    create_session,
    list_sessions,
    read_session,
)

runner = CliRunner()


def _make_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")
    return kb


class TestCreateSession:
    def test_create(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        session = create_session(kb, "baseflow review")
        assert session.id == "baseflow-review"
        assert session.name == "baseflow review"
        assert not session.closed

    def test_duplicate_raises(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        create_session(kb, "test session")
        import pytest

        with pytest.raises(ValueError, match="already exists"):
            create_session(kb, "test session")


class TestAddToSession:
    def test_add_entry(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        create_session(kb, "test")
        entry = add_to_session(kb, "test", "Found paper on CN", agent="agent-1")
        assert entry.agent == "agent-1"
        assert entry.content == "Found paper on CN"

    def test_add_with_tags(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        create_session(kb, "test")
        entry = add_to_session(kb, "test", "Key finding", tags=["key", "parameter"])
        assert "key" in entry.tags

    def test_add_to_closed_raises(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        create_session(kb, "test")
        close_session(kb, "test")
        import pytest

        with pytest.raises(ValueError, match="closed"):
            add_to_session(kb, "test", "Should fail")

    def test_add_to_nonexistent_raises(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        import pytest

        with pytest.raises(ValueError, match="not found"):
            add_to_session(kb, "nonexistent", "content")


class TestReadSession:
    def test_read_all(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        create_session(kb, "test")
        add_to_session(kb, "test", "Entry 1")
        add_to_session(kb, "test", "Entry 2")

        session = read_session(kb, "test")
        assert session is not None
        assert len(session.entries) == 2

    def test_read_filter_by_tag(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        create_session(kb, "test")
        add_to_session(kb, "test", "Tagged", tags=["key"])
        add_to_session(kb, "test", "Untagged")

        session = read_session(kb, "test", tag="key")
        assert session is not None
        assert len(session.entries) == 1
        assert session.entries[0].content == "Tagged"

    def test_read_nonexistent(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        assert read_session(kb, "nonexistent") is None


class TestListSessions:
    def test_list_empty(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        assert list_sessions(kb) == []

    def test_list_multiple(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        create_session(kb, "session a")
        create_session(kb, "session b")
        sessions = list_sessions(kb)
        assert len(sessions) == 2


class TestSessionCLI:
    def test_create_and_read(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        result = runner.invoke(
            app, ["--kb", str(kb), "session", "create", "my research"]
        )
        assert result.exit_code == 0
        assert "my research" in result.output

        result = runner.invoke(
            app, ["--kb", str(kb), "session", "add", "my-research", "Found something"]
        )
        assert result.exit_code == 0

        result = runner.invoke(app, ["--kb", str(kb), "session", "read", "my-research"])
        assert result.exit_code == 0
        assert "Found something" in result.output

    def test_list(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        create_session(kb, "session one")
        result = runner.invoke(app, ["--kb", str(kb), "session", "list"])
        assert result.exit_code == 0
        assert "session one" in result.output

    def test_close(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        create_session(kb, "closeable")
        result = runner.invoke(app, ["--kb", str(kb), "session", "close", "closeable"])
        assert result.exit_code == 0
        assert "Closed" in result.output
