"""HydroFound MCP server — expose KB tools to AI assistants."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server import Server
from mcp.types import TextContent, Tool


def create_server(kb_path: Path) -> Server:
    """Create an MCP server bound to a knowledge base.

    Args:
        kb_path: Path to the HydroFound knowledge base.

    Returns:
        Configured MCP Server instance.
    """
    server = Server("hydrofound")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="query",
                description="Search the knowledge base",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "q": {"type": "string", "description": "Search query"},
                        "scope": {
                            "type": "string",
                            "enum": ["papers", "packages", "codebases"],
                            "description": "Limit to content type",
                        },
                        "topic": {
                            "type": "string",
                            "description": "Filter by topic",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 10,
                            "description": "Max results",
                        },
                    },
                    "required": ["q"],
                },
            ),
            Tool(
                name="get",
                description="Read a document by path",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path within the KB",
                        },
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="multi_get",
                description="Read multiple documents",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of relative paths",
                        },
                    },
                    "required": ["paths"],
                },
            ),
            Tool(
                name="catalog_stats",
                description="Knowledge base statistics",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="list_topics",
                description="Available topics",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="discover_papers",
                description="Search academic APIs for papers",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for academic papers",
                        },
                        "limit": {"type": "integer", "default": 10},
                        "source": {
                            "type": "string",
                            "enum": ["all", "semantic_scholar", "exa"],
                            "default": "all",
                        },
                    },
                    "required": ["query"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Route tool calls to the appropriate module."""
        if name == "query":
            return await _handle_query(kb_path, arguments)
        elif name == "get":
            return _handle_get(kb_path, arguments)
        elif name == "multi_get":
            return _handle_multi_get(kb_path, arguments)
        elif name == "catalog_stats":
            return _handle_catalog_stats(kb_path)
        elif name == "list_topics":
            return _handle_list_topics(kb_path)
        elif name == "discover_papers":
            return await _handle_discover(kb_path, arguments)
        raise ValueError(f"Unknown tool: {name}")

    return server


async def _handle_query(kb_path: Path, args: dict) -> list[TextContent]:
    """Handle search query.

    Args:
        kb_path: Knowledge base root path.
        args: Tool arguments including ``q``, optional ``scope``, ``topic``, ``limit``.

    Returns:
        Formatted search results as MCP TextContent.
    """
    from hydrofound.query.fallback import fallback_search
    from hydrofound.query.qmd import is_qmd_available, qmd_search

    q = args["q"]
    scope = args.get("scope", "")
    limit = args.get("limit", 10)

    if is_qmd_available():
        results = qmd_search(kb_path, q, scope=scope or "", limit=limit)
    else:
        results = fallback_search(kb_path, q, scope=scope or None, limit=limit)

    if not results:
        return [TextContent(type="text", text="No results found.")]

    lines = []
    for r in results:
        lines.append(
            f"## {r.title}\n**Path:** {r.path}\n**Score:** {r.score:.2f}\n\n{r.snippet}\n"
        )
    return [TextContent(type="text", text="\n---\n".join(lines))]


def _handle_get(kb_path: Path, args: dict) -> list[TextContent]:
    """Read a single document.

    Args:
        kb_path: Knowledge base root path.
        args: Tool arguments containing ``path``.

    Returns:
        File contents as MCP TextContent, or an error message.
    """
    rel_path = args["path"]
    # Path traversal protection
    full_path = (kb_path / rel_path).resolve()
    if not full_path.is_relative_to(kb_path.resolve()):
        return [
            TextContent(
                type="text",
                text=f"Error: path '{rel_path}' is outside the knowledge base.",
            )
        ]

    if not full_path.exists():
        return [TextContent(type="text", text=f"File not found: {rel_path}")]
    return [TextContent(type="text", text=full_path.read_text())]


def _handle_multi_get(kb_path: Path, args: dict) -> list[TextContent]:
    """Read multiple documents.

    Args:
        kb_path: Knowledge base root path.
        args: Tool arguments containing ``paths`` list.

    Returns:
        Concatenated file contents separated by horizontal rules.
    """
    texts = []
    for p in args["paths"]:
        full_path = (kb_path / p).resolve()
        if not full_path.is_relative_to(kb_path.resolve()):
            texts.append(f"## {p}\n\nError: path outside knowledge base.")
            continue
        if full_path.exists():
            texts.append(f"## {p}\n\n{full_path.read_text()}")
        else:
            texts.append(f"## {p}\n\nFile not found.")
    return [TextContent(type="text", text="\n\n---\n\n".join(texts))]


def _handle_catalog_stats(kb_path: Path) -> list[TextContent]:
    """Return catalog statistics.

    Args:
        kb_path: Knowledge base root path.

    Returns:
        JSON-formatted catalog statistics.
    """
    from hydrofound.catalog.index import CatalogIndex

    stats = CatalogIndex(kb_path).stats()
    return [TextContent(type="text", text=json.dumps(stats, indent=2))]


def _handle_list_topics(kb_path: Path) -> list[TextContent]:
    """Return list of topics.

    Args:
        kb_path: Knowledge base root path.

    Returns:
        JSON array of topic names.
    """
    from hydrofound.catalog.index import CatalogIndex

    stats = CatalogIndex(kb_path).stats()
    topics = list(stats.get("topics", {}).keys())
    return [TextContent(type="text", text=json.dumps(topics))]


async def _handle_discover(kb_path: Path, args: dict) -> list[TextContent]:
    """Search academic APIs.

    Args:
        kb_path: Knowledge base root path.
        args: Tool arguments including ``query``, optional ``source``, ``limit``.

    Returns:
        Formatted paper results as MCP TextContent.
    """
    from hydrofound.config import load_config
    from hydrofound.discovery.exa import ExaProvider
    from hydrofound.discovery.orchestrator import discover_papers
    from hydrofound.discovery.semantic_scholar import SemanticScholarProvider

    config = load_config(kb_path)
    providers = []

    source = args.get("source", "all")
    if source in ("all", "semantic_scholar"):
        providers.append(SemanticScholarProvider(api_key=config.semantic_scholar_key))
    if source in ("all", "exa") and config.exa_key:
        providers.append(ExaProvider(api_key=config.exa_key))

    if not providers:
        return [
            TextContent(
                type="text",
                text=(
                    "No search providers configured. "
                    "Set HYDROFOUND_EXA_KEY or HYDROFOUND_SEMANTIC_SCHOLAR_KEY."
                ),
            )
        ]

    results = await discover_papers(
        args["query"], providers, limit=args.get("limit", 10)
    )

    if not results:
        return [TextContent(type="text", text="No papers found.")]

    lines = []
    for r in results:
        oa = "✓ Open Access" if r.is_open_access else ""
        lines.append(
            f"**{r.title}**\n"
            f"Authors: {', '.join(r.authors) if r.authors else 'Unknown'}\n"
            f"Year: {r.year or 'Unknown'} | DOI: {r.doi or 'N/A'} | {oa}\n"
            f"{r.abstract[:200] + '...' if len(r.abstract) > 200 else r.abstract}"
        )
    return [TextContent(type="text", text="\n\n---\n\n".join(lines))]
