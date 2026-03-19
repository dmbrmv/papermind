"""PaperMind MCP server — expose KB tools to AI assistants.

Tool schemas are in mcp_tools/schemas.py.
Handler implementations are in mcp_tools/handlers.py.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server import Server

from papermind.mcp_tools import handlers as h
from papermind.mcp_tools.schemas import TOOLS


def create_server(kb_path: Path) -> Server:
    """Create an MCP server bound to a knowledge base.

    Args:
        kb_path: Path to the PaperMind knowledge base.

    Returns:
        Configured MCP Server instance.
    """
    server = Server("papermind")

    @server.list_tools()
    async def list_tools() -> list:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list:
        """Route tool calls to the appropriate handler."""
        dispatch = {
            "scan": lambda: h.handle_scan(kb_path, arguments),
            "summary": lambda: h.handle_summary(kb_path, arguments),
            "detail": lambda: h.handle_detail(kb_path, arguments),
            "get": lambda: h.handle_get(kb_path, arguments),
            "multi_get": lambda: h.handle_multi_get(kb_path, arguments),
            "catalog_stats": lambda: h.handle_catalog_stats(kb_path),
            "list_topics": lambda: h.handle_list_topics(kb_path),
            "discover_papers": lambda: h.handle_discover(kb_path, arguments),
            "watch_file": lambda: h.handle_watch(kb_path, arguments),
            "explain_concept": lambda: h.handle_explain(kb_path, arguments),
            "provenance": lambda: h.handle_provenance(arguments),
            "project_profile": lambda: h.handle_project_profile(kb_path, arguments),
            "equation_map": lambda: h.handle_equation_map(arguments),
            "resolve_refs": lambda: h.handle_resolve_refs(kb_path, arguments),
            "verify_implementation": lambda: h.handle_verify(kb_path, arguments),
            "session_create": lambda: h.handle_session_create(kb_path, arguments),
            "session_add": lambda: h.handle_session_add(kb_path, arguments),
            "session_read": lambda: h.handle_session_read(kb_path, arguments),
        }

        handler = dispatch.get(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")

        result = handler()
        # Await coroutines (async handlers)
        if hasattr(result, "__await__"):
            return await result
        return result

    return server
