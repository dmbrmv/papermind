"""MCP tool handler implementations."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.types import TextContent

from papermind.query.dispatch import run_search

# ---------------------------------------------------------------------------
# Search tools
# ---------------------------------------------------------------------------


async def handle_scan(kb_path: Path, args: dict) -> list[TextContent]:
    """Tier 1: titles + IDs + scores."""
    results = run_search(
        kb_path,
        args["q"],
        scope=args.get("scope", ""),
        topic=args.get("topic", ""),
        year_from=args.get("year_from"),
        limit=args.get("limit", 20),
    )
    if not results:
        return [TextContent(type="text", text="No results found.")]

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r.score:.1f}] {r.title} — {r.path}")
    return [TextContent(type="text", text="\n".join(lines))]


async def handle_summary(kb_path: Path, args: dict) -> list[TextContent]:
    """Tier 2: structured abstract + metadata."""
    import frontmatter as fm_lib

    results = run_search(
        kb_path,
        args["q"],
        scope=args.get("scope", ""),
        topic=args.get("topic", ""),
        year_from=args.get("year_from"),
        limit=args.get("limit", 5),
    )
    if not results:
        return [TextContent(type="text", text="No results found.")]

    budget = args.get("budget", 0)
    lines = []
    total_chars = 0

    for r in results:
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
        if budget and total_chars + len(block) > budget * 4:
            break
        lines.append(block)
        total_chars += len(block)

    return [TextContent(type="text", text="\n\n---\n\n".join(lines))]


def handle_detail(kb_path: Path, args: dict) -> list[TextContent]:
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
            content = content[:max_chars] + "\n\n[...truncated...]"

    return [TextContent(type="text", text=content)]


# ---------------------------------------------------------------------------
# Direct access
# ---------------------------------------------------------------------------


def handle_get(kb_path: Path, args: dict) -> list[TextContent]:
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


def handle_multi_get(kb_path: Path, args: dict) -> list[TextContent]:
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


def handle_catalog_stats(kb_path: Path) -> list[TextContent]:
    """Return catalog statistics."""
    from papermind.catalog.index import CatalogIndex

    stats = CatalogIndex(kb_path).stats()
    return [TextContent(type="text", text=json.dumps(stats, indent=2))]


def handle_list_topics(kb_path: Path) -> list[TextContent]:
    """Return list of topics."""
    from papermind.catalog.index import CatalogIndex

    stats = CatalogIndex(kb_path).stats()
    topics = list(stats.get("topics", {}).keys())
    return [TextContent(type="text", text=json.dumps(topics))]


async def handle_discover(kb_path: Path, args: dict) -> list[TextContent]:
    """Search academic APIs."""
    from papermind.config import load_config
    from papermind.discovery.orchestrator import discover_papers
    from papermind.discovery.providers import build_providers

    config = load_config(kb_path)
    source = args.get("source", "all")
    providers = build_providers(source, config)

    if not providers:
        return [TextContent(type="text", text="No search providers configured.")]

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
# Analysis tools
# ---------------------------------------------------------------------------


def handle_watch(kb_path: Path, args: dict) -> list[TextContent]:
    """Surface relevant KB entries for a source file."""
    from papermind.watch import format_watch_output, watch_file

    file_path = Path(args["file_path"])
    limit = args.get("limit", 5)

    if not file_path.exists():
        return [TextContent(type="text", text=f"File not found: {file_path}")]

    results = watch_file(file_path, kb_path, limit=limit)
    return [
        TextContent(
            type="text",
            text=format_watch_output(file_path.name, results),
        )
    ]


def handle_explain(kb_path: Path, args: dict) -> list[TextContent]:
    """Look up a concept in the glossary or KB."""
    from papermind.explain import explain, format_explain

    concept = args["concept"]
    result = explain(concept, kb_path=kb_path)

    if result is None:
        return [
            TextContent(
                type="text",
                text=f"No explanation found for '{concept}'.",
            )
        ]
    return [TextContent(type="text", text=format_explain(result))]


def handle_equation_map(args: dict) -> list[TextContent]:
    """Map equation symbols to code variables."""
    from papermind.equation_map import (
        format_equation_map,
        map_equation_to_code,
    )

    file_path = Path(args["file_path"])
    if not file_path.exists():
        return [TextContent(type="text", text=f"File not found: {file_path}")]

    result = map_equation_to_code(
        args["equation_latex"], file_path, args.get("function_name")
    )
    return [TextContent(type="text", text=format_equation_map(result))]


def handle_provenance(args: dict) -> list[TextContent]:
    """Extract provenance annotations from a source file."""
    from papermind.provenance import extract_provenance, format_provenance

    file_path = Path(args["file_path"])
    if not file_path.exists():
        return [TextContent(type="text", text=f"File not found: {file_path}")]

    refs = extract_provenance(file_path)
    return [TextContent(type="text", text=format_provenance(refs))]


def handle_project_profile(kb_path: Path, args: dict) -> list[TextContent]:
    """Generate a project profile."""
    from papermind.profile import format_profile, generate_profile

    codebase_path = Path(args["codebase_path"])
    if not codebase_path.is_dir():
        return [TextContent(type="text", text=f"Not a directory: {codebase_path}")]

    profile = generate_profile(codebase_path, kb_path)
    return [TextContent(type="text", text=format_profile(profile))]


def handle_verify(kb_path: Path, args: dict) -> list[TextContent]:
    """Verify code implements a paper equation."""
    from papermind.verify import format_verification, verify_implementation

    file_path = Path(args["file_path"])
    if not file_path.exists():
        return [TextContent(type="text", text=f"File not found: {file_path}")]

    result = verify_implementation(
        args["paper_id"],
        args["equation_number"],
        file_path,
        args.get("function_name"),
        kb_path,
    )
    return [TextContent(type="text", text=format_verification(result))]


def handle_resolve_refs(kb_path: Path, args: dict) -> list[TextContent]:
    """Resolve kb: references in markdown text."""
    from papermind.memory import (
        extract_kb_refs,
        format_resolved_refs,
        resolve_refs,
    )

    text = args["text"]
    refs = extract_kb_refs(text)
    if not refs:
        return [TextContent(type="text", text="No kb: references found in text.")]

    resolved = resolve_refs(refs, kb_path)
    return [TextContent(type="text", text=format_resolved_refs(resolved))]


# ---------------------------------------------------------------------------
# Session tools
# ---------------------------------------------------------------------------


def handle_session_create(kb_path: Path, args: dict) -> list[TextContent]:
    """Create a research session."""
    from papermind.session import create_session

    try:
        session = create_session(kb_path, args["name"])
        return [
            TextContent(
                type="text",
                text=(f"Created session '{session.name}' (id: {session.id})"),
            )
        ]
    except ValueError as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


def handle_session_add(kb_path: Path, args: dict) -> list[TextContent]:
    """Add entry to a research session."""
    from papermind.session import add_to_session

    try:
        entry = add_to_session(
            kb_path,
            args["session_id"],
            args["content"],
            agent=args.get("agent", "agent"),
            tags=args.get("tags"),
        )
        return [
            TextContent(
                type="text",
                text=(f"Added entry by {entry.agent} at {entry.timestamp}"),
            )
        ]
    except ValueError as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


def handle_session_read(kb_path: Path, args: dict) -> list[TextContent]:
    """Read a research session."""
    from papermind.session import format_session, read_session

    session = read_session(kb_path, args["session_id"], tag=args.get("tag", ""))
    if session is None:
        return [
            TextContent(
                type="text",
                text=f"Session not found: {args['session_id']}",
            )
        ]
    return [TextContent(type="text", text=format_session(session))]
