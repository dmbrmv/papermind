"""papermind chat — RAG-powered Q&A with a local LLM via ollama."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import httpx
import typer
from rich.console import Console

if TYPE_CHECKING:
    from pathlib import Path

from papermind.cli.utils import _resolve_kb

console = Console()

OLLAMA_URL = "http://localhost:11434/api/generate"

SYSTEM_PROMPT = """\
You are a research assistant with access to a curated scientific knowledge base. \
Use the following context to answer the question. If the context doesn't contain \
relevant information, say so.

--- Knowledge Base Context ---
{context}
--- End Context ---"""


def _build_briefing(kb_path: Path, topic: str, max_tokens: int) -> str:
    """Build a context-pack briefing string for the given topic.

    Reuses the same logic as the context-pack command.
    """
    import frontmatter as fm_lib

    from papermind.catalog.index import CatalogIndex

    kb = kb_path
    catalog = CatalogIndex(kb)
    entries = [e for e in catalog.entries if e.topic == topic]

    if not entries:
        return ""

    papers: list[dict] = []
    for entry in entries:
        md_path = kb / entry.path
        if not md_path.exists():
            continue
        try:
            post = fm_lib.load(md_path)
            meta = dict(post.metadata)
            meta["_path"] = entry.path
            papers.append(meta)
        except Exception:
            continue

    if not papers:
        return ""

    papers.sort(
        key=lambda p: len(p.get("cites", [])) + len(p.get("cited_by", [])),
        reverse=True,
    )

    max_chars = max_tokens * 4
    lines = [f"# PaperMind Briefing: {topic}", f"> {len(papers)} papers in KB", ""]
    total_chars = sum(len(line) for line in lines)

    for i, p in enumerate(papers, 1):
        title = p.get("title", "Untitled")
        doi = p.get("doi", "")
        year = p.get("year", "")
        abstract = p.get("abstract", "")
        tags = p.get("tags", [])

        block_lines = [f"## {i}. {title}"]
        meta_parts = []
        if year:
            meta_parts.append(str(year))
        if doi:
            meta_parts.append(f"DOI: {doi}")
        if meta_parts:
            block_lines.append(" | ".join(meta_parts))
        if tags:
            block_lines.append(f"Tags: {', '.join(tags[:5])}")
        if abstract:
            max_abstract = min(200, (max_chars - total_chars) // 3)
            if max_abstract > 50:
                trunc = (
                    abstract[:max_abstract] + "..."
                    if len(abstract) > max_abstract
                    else abstract
                )
                block_lines.append(f"\n{trunc}")

        block_lines.append("")
        block = "\n".join(block_lines)

        if total_chars + len(block) > max_chars:
            lines.append(f"\n*...{len(papers) - i + 1} more papers truncated*")
            break
        lines.append(block)
        total_chars += len(block)

    return "\n".join(lines)


def chat_cmd(
    ctx: typer.Context,
    question: str = typer.Argument(..., help="Question to ask the knowledge base"),
    topic: str = typer.Option(
        "",
        "--topic",
        "-t",
        help="Filter context to a specific topic",
    ),
    max_context: int = typer.Option(
        4000,
        "--max-context",
        help="Max tokens for KB context sent to LLM",
    ),
    model: str = typer.Option(
        "llama3",
        "--model",
        "-m",
        help="Ollama model to use",
    ),
) -> None:
    """Ask a question using KB context and a local LLM (ollama).

    Generates a context briefing from the knowledge base, sends it
    with the question to ollama, and streams the response.

    Examples::

        papermind chat "How does SWAT+ handle groundwater?" --topic hydrology
        papermind chat "Compare LSTM and transformer for streamflow" -m mistral
    """
    kb = _resolve_kb(ctx)

    # Build context from KB
    context = ""
    if topic:
        context = _build_briefing(kb, topic, max_context)
        if not context:
            console.print(
                f"[yellow]No papers found for topic[/yellow] {topic!r}. "
                "Proceeding without KB context."
            )

    system = SYSTEM_PROMPT.format(
        context=context if context else "(no context available)"
    )

    # Stream from ollama
    payload = {
        "model": model,
        "prompt": question,
        "system": system,
        "stream": True,
    }

    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=120.0, write=5.0, pool=5.0)
        ) as client:
            with client.stream("POST", OLLAMA_URL, json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    if token:
                        sys.stdout.write(token)
                        sys.stdout.flush()
                    if chunk.get("done"):
                        break
        # Final newline after streaming
        sys.stdout.write("\n")
        sys.stdout.flush()
    except httpx.ConnectError:
        console.print(
            "[red]Cannot connect to ollama[/red] at localhost:11434.\n"
            "Make sure ollama is running: [bold]ollama serve[/bold]"
        )
        raise typer.Exit(code=1)
    except httpx.HTTPStatusError as exc:
        msg = exc.response.text[:200]
        console.print(f"[red]Ollama error:[/red] {exc.response.status_code} — {msg}")
        raise typer.Exit(code=1)
