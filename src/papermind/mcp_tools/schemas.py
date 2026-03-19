"""MCP tool schema definitions — input schemas for all 19 tools."""

from __future__ import annotations

from mcp.types import Tool

TOOLS: list[Tool] = [
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
                "topic": {"type": "string", "description": "Filter by topic"},
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
            "~500 tokens per result."
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
                "limit": {"type": "integer", "default": 5},
                "budget": {
                    "type": "integer",
                    "description": "Max output tokens (approximate).",
                },
            },
            "required": ["q"],
        },
    ),
    Tool(
        name="detail",
        description="Full document read — complete text, equations, figures.",
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
                "query": {"type": "string", "description": "Search query"},
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
            "Surface relevant KB entries for a source code file. ~50 tokens per result."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to source file",
                },
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="explain_concept",
        description=(
            "Explain a hydrological parameter or scientific concept. "
            "Returns definition, range, units, and reference."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "concept": {
                    "type": "string",
                    "description": "Parameter name or concept",
                },
            },
            "required": ["concept"],
        },
    ),
    Tool(
        name="session_create",
        description="Create a research session.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Session name"},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="session_add",
        description="Add a finding to a research session.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID",
                },
                "content": {
                    "type": "string",
                    "description": "Finding or note",
                },
                "agent": {"type": "string", "description": "Agent name"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags",
                },
            },
            "required": ["session_id", "content"],
        },
    ),
    Tool(
        name="session_read",
        description="Read findings from a research session.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID",
                },
                "tag": {"type": "string", "description": "Filter by tag"},
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="resolve_refs",
        description="Resolve kb:paper-id references in markdown text.",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Markdown text with kb: references",
                },
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="verify_implementation",
        description="Verify code implements a paper equation.",
        inputSchema={
            "type": "object",
            "properties": {
                "paper_id": {
                    "type": "string",
                    "description": "Paper ID in the KB",
                },
                "equation_number": {
                    "type": "string",
                    "description": "Equation number (e.g. '4.2')",
                },
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to source file",
                },
                "function_name": {
                    "type": "string",
                    "description": "Optional function name",
                },
            },
            "required": ["paper_id", "equation_number", "file_path"],
        },
    ),
    Tool(
        name="equation_map",
        description="Map LaTeX equation symbols to code variables.",
        inputSchema={
            "type": "object",
            "properties": {
                "equation_latex": {
                    "type": "string",
                    "description": "LaTeX equation string",
                },
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to source file",
                },
                "function_name": {
                    "type": "string",
                    "description": "Optional function name",
                },
            },
            "required": ["equation_latex", "file_path"],
        },
    ),
    Tool(
        name="provenance",
        description="Extract # REF: annotations from a source file.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to source file",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="project_profile",
        description="Generate a project profile from codebase analysis.",
        inputSchema={
            "type": "object",
            "properties": {
                "codebase_path": {
                    "type": "string",
                    "description": "Absolute path to codebase root",
                },
            },
            "required": ["codebase_path"],
        },
    ),
]
