"""PaperMind MCP server — expose KB tools to AI assistants."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server import Server
from mcp.types import TextContent, Tool


def create_server(kb_path: Path) -> Server:
    """Create an MCP server bound to a knowledge base.

    Args:
        kb_path: Path to the PaperMind knowledge base.

    Returns:
        Configured MCP Server instance.
    """
    server = Server("papermind")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="scan",
                description=(
                    "Fast triage search — returns titles, IDs, and scores. "
                    "~50 tokens per result. Use to decide what's worth reading."
                ),
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
                        "year_from": {
                            "type": "integer",
                            "description": "Papers from this year onward",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 20,
                            "description": "Max results",
                        },
                    },
                    "required": ["q"],
                },
            ),
            Tool(
                name="summary",
                description=(
                    "Structured summaries — title, abstract, metadata, DOI. "
                    "~500 tokens per result. Use to decide what's worth "
                    "a full read."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "q": {"type": "string", "description": "Search query"},
                        "scope": {
                            "type": "string",
                            "enum": ["papers", "packages", "codebases"],
                        },
                        "topic": {"type": "string"},
                        "limit": {
                            "type": "integer",
                            "default": 5,
                        },
                        "budget": {
                            "type": "integer",
                            "description": (
                                "Max output tokens (approximate). "
                                "Results are truncated to fit."
                            ),
                        },
                    },
                    "required": ["q"],
                },
            ),
            Tool(
                name="detail",
                description=(
                    "Full document read — complete text, equations, figures. "
                    "~3000 tokens per result. Use when you need the actual "
                    "content."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from scan/summary",
                        },
                        "budget": {
                            "type": "integer",
                            "description": "Max output tokens (approximate)",
                        },
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="get",
                description="Read a document by path (raw content)",
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
                            "description": "Search query",
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
            Tool(
                name="watch_file",
                description=(
                    "Surface relevant KB entries for a source code file. "
                    "Extracts concepts (imports, functions, docstrings) "
                    "and searches the KB. ~50 tokens per result."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute path to source file",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 5,
                        },
                    },
                    "required": ["file_path"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Route tool calls to the appropriate handler."""
        if name == "scan":
            return await _handle_scan(kb_path, arguments)
        elif name == "summary":
            return await _handle_summary(kb_path, arguments)
        elif name == "detail":
            return _handle_detail(kb_path, arguments)
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
        elif name == "watch_file":
            return _handle_watch(kb_path, arguments)
        raise ValueError(f"Unknown tool: {name}")

    return server


# ---------------------------------------------------------------------------
# Tiered retrieval: scan → summary → detail
# ---------------------------------------------------------------------------


async def _handle_scan(kb_path: Path, args: dict) -> list[TextContent]:
    """Tier 1: titles + IDs + scores. ~50 tokens per result."""
    results = _search(kb_path, args)
    if not results:
        return [TextContent(type="text", text="No results found.")]

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r.score:.1f}] {r.title} — {r.path}")
    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_summary(kb_path: Path, args: dict) -> list[TextContent]:
    """Tier 2: structured abstract + metadata. ~500 tokens per result."""
    import frontmatter as fm_lib

    results = _search(kb_path, args)
    if not results:
        return [TextContent(type="text", text="No results found.")]

    budget = args.get("budget", 0)
    lines = []
    total_chars = 0

    for r in results:
        # Read frontmatter for rich metadata
        full_path = kb_path / r.path
        meta: dict = {}
        if full_path.exists():
            try:
                post = fm_lib.load(full_path)
                meta = dict(post.metadata)
            except Exception:
                pass

        entry_lines = [f"## {r.title}"]
        entry_lines.append(f"**Path:** {r.path}")
        if meta.get("doi"):
            entry_lines.append(f"**DOI:** {meta['doi']}")
        if meta.get("year"):
            entry_lines.append(f"**Year:** {meta['year']}")
        if meta.get("topic"):
            entry_lines.append(f"**Topic:** {meta['topic']}")

        abstract = meta.get("abstract", "")
        if abstract:
            entry_lines.append(f"**Abstract:** {abstract[:300]}")
        elif r.snippet:
            entry_lines.append(f"**Snippet:** {r.snippet[:200]}")

        cites = meta.get("cites", [])
        cited_by = meta.get("cited_by", [])
        if cites or cited_by:
            entry_lines.append(
                f"**Citations:** {len(cites)} refs, {len(cited_by)} cited by"
            )

        block = "\n".join(entry_lines)

        # Budget enforcement (rough: 1 token ≈ 4 chars)
        if budget and total_chars + len(block) > budget * 4:
            break
        lines.append(block)
        total_chars += len(block)

    return [TextContent(type="text", text="\n\n---\n\n".join(lines))]


def _handle_detail(kb_path: Path, args: dict) -> list[TextContent]:
    """Tier 3: full document content."""

    rel_path = args["path"]
    full_path = (kb_path / rel_path).resolve()

    if not full_path.is_relative_to(kb_path.resolve()):
        return [
            TextContent(
                type="text",
                text=f"Error: path '{rel_path}' is outside the KB.",
            )
        ]
    if not full_path.exists():
        return [TextContent(type="text", text=f"File not found: {rel_path}")]

    content = full_path.read_text()
    budget = args.get("budget", 0)
    if budget:
        max_chars = budget * 4
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[...truncated to budget...]"

    return [TextContent(type="text", text=content)]


# ---------------------------------------------------------------------------
# Legacy tools (get, multi_get, catalog, topics, discover)
# ---------------------------------------------------------------------------


def _handle_get(kb_path: Path, args: dict) -> list[TextContent]:
    """Read a single document."""
    rel_path = args["path"]
    full_path = (kb_path / rel_path).resolve()
    if not full_path.is_relative_to(kb_path.resolve()):
        return [
            TextContent(
                type="text",
                text=f"Error: path '{rel_path}' is outside the KB.",
            )
        ]
    if not full_path.exists():
        return [TextContent(type="text", text=f"File not found: {rel_path}")]
    return [TextContent(type="text", text=full_path.read_text())]


def _handle_multi_get(kb_path: Path, args: dict) -> list[TextContent]:
    """Read multiple documents."""
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
    """Return catalog statistics."""
    from papermind.catalog.index import CatalogIndex

    stats = CatalogIndex(kb_path).stats()
    return [TextContent(type="text", text=json.dumps(stats, indent=2))]


def _handle_list_topics(kb_path: Path) -> list[TextContent]:
    """Return list of topics."""
    from papermind.catalog.index import CatalogIndex

    stats = CatalogIndex(kb_path).stats()
    topics = list(stats.get("topics", {}).keys())
    return [TextContent(type="text", text=json.dumps(topics))]


async def _handle_discover(kb_path: Path, args: dict) -> list[TextContent]:
    """Search academic APIs."""
    from papermind.config import load_config
    from papermind.discovery.exa import ExaProvider
    from papermind.discovery.orchestrator import discover_papers
    from papermind.discovery.semantic_scholar import SemanticScholarProvider

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
                text="No search providers configured.",
            )
        ]

    results = await discover_papers(
        args["query"], providers, limit=args.get("limit", 10)
    )

    if not results:
        return [TextContent(type="text", text="No papers found.")]

    lines = []
    for r in results:
        oa = "Open Access" if r.is_open_access else ""
        lines.append(
            f"**{r.title}**\n"
            f"Year: {r.year or '?'} | DOI: {r.doi or 'N/A'}"
            f"{' | ' + oa if oa else ''}\n"
            f"{(r.abstract or '')[:200]}"
        )
    return [TextContent(type="text", text="\n\n---\n\n".join(lines))]


# ---------------------------------------------------------------------------
# Shared search helper
# ---------------------------------------------------------------------------


def _handle_watch(kb_path: Path, args: dict) -> list[TextContent]:
    """Surface relevant KB entries for a source file."""
    from papermind.watch import format_watch_output, watch_file

    file_path = Path(args["file_path"])
    limit = args.get("limit", 5)

    if not file_path.exists():
        return [
            TextContent(
                type="text",
                text=f"File not found: {file_path}",
            )
        ]

    results = watch_file(file_path, kb_path, limit=limit)
    return [
        TextContent(
            type="text",
            text=format_watch_output(file_path.name, results),
        )
    ]


def _search(kb_path: Path, args: dict) -> list:
    """Run search using qmd or fallback."""
    from papermind.query.fallback import fallback_search
    from papermind.query.qmd import is_qmd_available, qmd_search

    q = args["q"]
    scope = args.get("scope", "")
    topic = args.get("topic", "")
    year_from = args.get("year_from")
    limit = args.get("limit", 10)

    if is_qmd_available():
        return qmd_search(kb_path, q, scope=scope or "", limit=limit)
    return fallback_search(
        kb_path,
        q,
        scope=scope or None,
        topic=topic or None,
        year_from=year_from,
        limit=limit,
    )
