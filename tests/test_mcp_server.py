"""Tests for the PaperMind MCP server handlers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from mcp.types import TextContent

from papermind.mcp_server import (
    _handle_catalog_stats,
    _handle_get,
    _handle_list_topics,
    _handle_multi_get,
    _handle_query,
    create_server,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def kb_root(tmp_path: Path) -> Path:
    """Minimal knowledge base directory for testing."""
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir()
    (papers_dir / "test_paper.md").write_text(
        "---\ntitle: Test Paper\ntopic: hydrology\n---\n\nA paper about rivers."
    )
    return tmp_path


# ---------------------------------------------------------------------------
# create_server
# ---------------------------------------------------------------------------


def test_create_server_returns_server(kb_root: Path) -> None:
    """create_server should return a configured Server instance."""
    from mcp.server import Server

    server = create_server(kb_root)
    assert isinstance(server, Server)


# ---------------------------------------------------------------------------
# list_tools — via the server's registered handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tools_returns_six_tools(kb_root: Path) -> None:
    """list_tools should return exactly 6 tools with the correct names."""
    server = create_server(kb_root)

    # The list_tools handler is stored in request_handlers; invoke it directly
    from mcp.types import ListToolsRequest

    handler = server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))

    # result is a ServerResult wrapping a ListToolsResult
    tools = result.root.tools
    assert len(tools) == 6

    names = {t.name for t in tools}
    assert names == {
        "query",
        "get",
        "multi_get",
        "catalog_stats",
        "list_topics",
        "discover_papers",
    }


@pytest.mark.asyncio
async def test_list_tools_query_has_required_field(kb_root: Path) -> None:
    """The 'query' tool should declare 'q' as a required field."""
    server = create_server(kb_root)
    from mcp.types import ListToolsRequest

    handler = server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))
    tools_by_name = {t.name: t for t in result.root.tools}
    assert "q" in tools_by_name["query"].inputSchema["required"]


# ---------------------------------------------------------------------------
# _handle_query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_query_returns_results(kb_root: Path) -> None:
    """_handle_query should return formatted results for a matching query."""
    from papermind.query.fallback import SearchResult

    mock_results = [
        SearchResult(
            path="papers/test_paper.md",
            title="Test Paper",
            snippet="A paper about rivers.",
            score=0.9,
        )
    ]
    with (
        patch("papermind.query.qmd.is_qmd_available", return_value=False),
        patch("papermind.query.fallback.fallback_search", return_value=mock_results),
    ):
        response = await _handle_query(kb_root, {"q": "rivers", "limit": 10})

    assert len(response) == 1
    assert isinstance(response[0], TextContent)
    assert "Test Paper" in response[0].text
    assert "papers/test_paper.md" in response[0].text


@pytest.mark.asyncio
async def test_handle_query_no_results(kb_root: Path) -> None:
    """_handle_query should return a 'No results found.' message when empty."""
    with (
        patch("papermind.query.qmd.is_qmd_available", return_value=False),
        patch("papermind.query.fallback.fallback_search", return_value=[]),
    ):
        response = await _handle_query(kb_root, {"q": "xyzzy"})

    assert response[0].text == "No results found."


# ---------------------------------------------------------------------------
# _handle_get
# ---------------------------------------------------------------------------


def test_handle_get_reads_file(kb_root: Path) -> None:
    """_handle_get should return file contents for a valid path."""
    response = _handle_get(kb_root, {"path": "papers/test_paper.md"})

    assert len(response) == 1
    assert isinstance(response[0], TextContent)
    assert "A paper about rivers." in response[0].text


def test_handle_get_missing_file(kb_root: Path) -> None:
    """_handle_get should return a 'File not found' message for missing paths."""
    response = _handle_get(kb_root, {"path": "papers/nonexistent.md"})

    assert "File not found" in response[0].text


def test_handle_get_path_traversal_rejected(kb_root: Path) -> None:
    """_handle_get should reject paths that escape the knowledge base root."""
    response = _handle_get(kb_root, {"path": "../../etc/passwd"})

    assert "outside the knowledge base" in response[0].text


def test_handle_get_path_traversal_via_absolute(kb_root: Path) -> None:
    """_handle_get should reject absolute paths pointing outside the KB."""
    response = _handle_get(kb_root, {"path": "/etc/passwd"})

    assert "outside the knowledge base" in response[0].text


# ---------------------------------------------------------------------------
# _handle_multi_get
# ---------------------------------------------------------------------------


def test_handle_multi_get_reads_multiple(kb_root: Path) -> None:
    """_handle_multi_get should return concatenated contents for valid paths."""
    (kb_root / "papers" / "second.md").write_text("Second document.")
    response = _handle_multi_get(
        kb_root,
        {"paths": ["papers/test_paper.md", "papers/second.md"]},
    )

    assert len(response) == 1
    text = response[0].text
    assert "papers/test_paper.md" in text
    assert "papers/second.md" in text
    assert "A paper about rivers." in text
    assert "Second document." in text


def test_handle_multi_get_missing_file(kb_root: Path) -> None:
    """_handle_multi_get should report 'File not found' for missing paths."""
    response = _handle_multi_get(kb_root, {"paths": ["papers/missing.md"]})

    assert "File not found" in response[0].text


def test_handle_multi_get_path_traversal_rejected(kb_root: Path) -> None:
    """_handle_multi_get should reject paths that escape the KB root."""
    response = _handle_multi_get(kb_root, {"paths": ["../../etc/passwd"]})

    assert "outside knowledge base" in response[0].text


# ---------------------------------------------------------------------------
# _handle_catalog_stats
# ---------------------------------------------------------------------------


def test_handle_catalog_stats_returns_json(kb_root: Path) -> None:
    """_handle_catalog_stats should return valid JSON stats."""
    mock_stats = {"total": 5, "topics": {"hydrology": 3, "ml": 2}}
    with patch("papermind.catalog.index.CatalogIndex.stats", return_value=mock_stats):
        response = _handle_catalog_stats(kb_root)

    assert len(response) == 1
    parsed = json.loads(response[0].text)
    assert parsed["total"] == 5
    assert "topics" in parsed


# ---------------------------------------------------------------------------
# _handle_list_topics
# ---------------------------------------------------------------------------


def test_handle_list_topics_returns_list(kb_root: Path) -> None:
    """_handle_list_topics should return a JSON array of topic names."""
    mock_stats = {"topics": {"hydrology": 3, "ml": 2}}
    with patch("papermind.catalog.index.CatalogIndex.stats", return_value=mock_stats):
        response = _handle_list_topics(kb_root)

    assert len(response) == 1
    topics = json.loads(response[0].text)
    assert isinstance(topics, list)
    assert set(topics) == {"hydrology", "ml"}


def test_handle_list_topics_empty_catalog(kb_root: Path) -> None:
    """_handle_list_topics should return an empty list when no topics exist."""
    with patch("papermind.catalog.index.CatalogIndex.stats", return_value={}):
        response = _handle_list_topics(kb_root)

    assert json.loads(response[0].text) == []
