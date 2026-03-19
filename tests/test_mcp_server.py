"""Tests for the PaperMind MCP server handlers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from mcp.types import TextContent

from papermind.mcp_server import create_server
from papermind.mcp_tools.handlers import (
    handle_catalog_stats as _handle_catalog_stats,
)
from papermind.mcp_tools.handlers import (
    handle_detail as _handle_detail,
)
from papermind.mcp_tools.handlers import (
    handle_get as _handle_get,
)
from papermind.mcp_tools.handlers import (
    handle_list_topics as _handle_list_topics,
)
from papermind.mcp_tools.handlers import (
    handle_multi_get as _handle_multi_get,
)
from papermind.mcp_tools.handlers import (
    handle_scan as _handle_scan,
)
from papermind.mcp_tools.handlers import (
    handle_summary as _handle_summary,
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
        "---\ntitle: Test Paper\ntopic: hydrology\n"
        "doi: '10.1/test'\nabstract: A paper about rivers.\n---\n\n"
        "A paper about rivers and hydrology."
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
# list_tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tools_returns_expected_tools(kb_root: Path) -> None:
    """list_tools should return tools including tiered retrieval."""
    server = create_server(kb_root)
    from mcp.types import ListToolsRequest

    handler = server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))

    tools = result.root.tools
    names = {t.name for t in tools}
    assert "scan" in names
    assert "summary" in names
    assert "detail" in names
    assert "get" in names
    assert "catalog_stats" in names
    assert "discover_papers" in names


@pytest.mark.asyncio
async def test_list_tools_scan_has_required_field(kb_root: Path) -> None:
    """The 'scan' tool should declare 'q' as a required field."""
    server = create_server(kb_root)
    from mcp.types import ListToolsRequest

    handler = server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))
    tools_by_name = {t.name: t for t in result.root.tools}
    assert "q" in tools_by_name["scan"].inputSchema["required"]


# ---------------------------------------------------------------------------
# _handle_scan (tier 1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_scan_returns_results(kb_root: Path) -> None:
    """_handle_scan should return compact results with titles and paths."""
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
        patch(
            "papermind.query.fallback.fallback_search",
            return_value=mock_results,
        ),
    ):
        response = await _handle_scan(kb_root, {"q": "rivers", "limit": 10})

    assert len(response) == 1
    assert isinstance(response[0], TextContent)
    assert "Test Paper" in response[0].text
    assert "papers/test_paper.md" in response[0].text


@pytest.mark.asyncio
async def test_handle_scan_no_results(kb_root: Path) -> None:
    """_handle_scan should return 'No results found.' when empty."""
    with (
        patch("papermind.query.qmd.is_qmd_available", return_value=False),
        patch("papermind.query.fallback.fallback_search", return_value=[]),
    ):
        response = await _handle_scan(kb_root, {"q": "xyzzy"})

    assert response[0].text == "No results found."


# ---------------------------------------------------------------------------
# _handle_summary (tier 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_summary_includes_metadata(kb_root: Path) -> None:
    """_handle_summary should include DOI, topic, abstract from frontmatter."""
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
        patch(
            "papermind.query.fallback.fallback_search",
            return_value=mock_results,
        ),
    ):
        response = await _handle_summary(kb_root, {"q": "rivers", "limit": 5})

    text = response[0].text
    assert "Test Paper" in text
    assert "10.1/test" in text
    assert "hydrology" in text


@pytest.mark.asyncio
async def test_handle_summary_respects_budget(kb_root: Path) -> None:
    """_handle_summary with budget=50 should produce short output."""
    from papermind.query.fallback import SearchResult

    mock_results = [
        SearchResult(
            path="papers/test_paper.md",
            title="Test Paper",
            snippet="A" * 500,
            score=0.9,
        ),
        SearchResult(
            path="papers/second.md",
            title="Second Paper",
            snippet="B" * 500,
            score=0.8,
        ),
    ]
    with (
        patch("papermind.query.qmd.is_qmd_available", return_value=False),
        patch(
            "papermind.query.fallback.fallback_search",
            return_value=mock_results,
        ),
    ):
        response = await _handle_summary(kb_root, {"q": "test", "budget": 50})

    # Budget of 50 tokens ≈ 200 chars — should only fit 1 result
    assert "Second Paper" not in response[0].text


# ---------------------------------------------------------------------------
# _handle_detail (tier 3)
# ---------------------------------------------------------------------------


def test_handle_detail_returns_full_content(kb_root: Path) -> None:
    """_handle_detail should return the full file content."""
    response = _handle_detail(kb_root, {"path": "papers/test_paper.md"})
    assert "A paper about rivers" in response[0].text


def test_handle_detail_respects_budget(kb_root: Path) -> None:
    """_handle_detail with budget should truncate long content."""
    # Write a large file
    (kb_root / "papers" / "big.md").write_text("x" * 10000)
    response = _handle_detail(kb_root, {"path": "papers/big.md", "budget": 100})
    assert "[...truncated" in response[0].text
    assert len(response[0].text) < 1000


def test_handle_detail_path_traversal(kb_root: Path) -> None:
    """_handle_detail should reject paths outside the KB."""
    response = _handle_detail(kb_root, {"path": "../../etc/passwd"})
    assert "outside the KB" in response[0].text


# ---------------------------------------------------------------------------
# _handle_get (legacy)
# ---------------------------------------------------------------------------


def test_handle_get_reads_file(kb_root: Path) -> None:
    """_handle_get should return file contents for a valid path."""
    response = _handle_get(kb_root, {"path": "papers/test_paper.md"})
    assert len(response) == 1
    assert "A paper about rivers" in response[0].text


def test_handle_get_missing_file(kb_root: Path) -> None:
    """_handle_get should return 'File not found' for missing paths."""
    response = _handle_get(kb_root, {"path": "papers/nonexistent.md"})
    assert "File not found" in response[0].text


def test_handle_get_path_traversal_rejected(kb_root: Path) -> None:
    """_handle_get should reject paths that escape the KB root."""
    response = _handle_get(kb_root, {"path": "../../etc/passwd"})
    assert "outside the KB" in response[0].text


# ---------------------------------------------------------------------------
# _handle_multi_get
# ---------------------------------------------------------------------------


def test_handle_multi_get_reads_multiple(kb_root: Path) -> None:
    """_handle_multi_get should return concatenated contents."""
    (kb_root / "papers" / "second.md").write_text("Second document.")
    response = _handle_multi_get(
        kb_root,
        {"paths": ["papers/test_paper.md", "papers/second.md"]},
    )
    text = response[0].text
    assert "papers/test_paper.md" in text
    assert "Second document." in text


def test_handle_multi_get_path_traversal_rejected(kb_root: Path) -> None:
    """_handle_multi_get should reject paths that escape the KB root."""
    response = _handle_multi_get(kb_root, {"paths": ["../../etc/passwd"]})
    assert "outside knowledge base" in response[0].text


# ---------------------------------------------------------------------------
# _handle_catalog_stats + _handle_list_topics
# ---------------------------------------------------------------------------


def test_handle_catalog_stats_returns_json(kb_root: Path) -> None:
    """_handle_catalog_stats should return valid JSON stats."""
    mock_stats = {"total": 5, "topics": {"hydrology": 3, "ml": 2}}
    with patch(
        "papermind.catalog.index.CatalogIndex.stats",
        return_value=mock_stats,
    ):
        response = _handle_catalog_stats(kb_root)
    parsed = json.loads(response[0].text)
    assert parsed["total"] == 5


def test_handle_list_topics_returns_list(kb_root: Path) -> None:
    """_handle_list_topics should return a JSON array of topic names."""
    mock_stats = {"topics": {"hydrology": 3, "ml": 2}}
    with patch(
        "papermind.catalog.index.CatalogIndex.stats",
        return_value=mock_stats,
    ):
        response = _handle_list_topics(kb_root)
    topics = json.loads(response[0].text)
    assert set(topics) == {"hydrology", "ml"}


def test_handle_list_topics_empty_catalog(kb_root: Path) -> None:
    """_handle_list_topics should return empty list when no topics."""
    with patch(
        "papermind.catalog.index.CatalogIndex.stats",
        return_value={},
    ):
        response = _handle_list_topics(kb_root)
    assert json.loads(response[0].text) == []
