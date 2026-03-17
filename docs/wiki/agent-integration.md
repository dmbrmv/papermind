# Agent Integration

## MCP server setup for Claude Code

Add to `.claude/mcp.json` in your project:

```json
{
  "mcpServers": {
    "papermind": {
      "command": "papermind",
      "args": ["--kb", "/home/user/Documents/KnowledgeBase", "serve"]
    }
  }
}
```

The server starts automatically when Claude Code opens. It exposes the KB as tools available in any conversation.

If `papermind` is not on PATH (e.g., installed in a venv), use the full path:

```json
{
  "mcpServers": {
    "papermind": {
      "command": "/home/user/.venv/bin/papermind",
      "args": ["--kb", "/home/user/Documents/KnowledgeBase", "serve"]
    }
  }
}
```

## Available MCP tools

| Tool | Tier | Token cost | Use for |
|------|------|-----------|---------|
| `scan` | 1 | ~50/result | Identifying candidates from a large KB |
| `summary` | 2 | ~500/result | Qualifying papers before reading full text |
| `detail` | 3 | ~3000/result | Extracting equations, methods, full text |
| `get` | — | varies | Reading a document by known path |
| `multi_get` | — | varies | Batch-reading multiple documents |
| `catalog_stats` | — | small | KB overview (counts by type/topic) |
| `list_topics` | — | small | Available topics in the KB |
| `discover_papers` | — | small | Searching academic APIs without ingesting |
| `watch_file` | — | ~50/result | Surfacing KB entries relevant to a source file |

## Tiered retrieval pattern

Start narrow, escalate only when needed:

```
scan("SWAT calibration uncertainty")
  → 8 results, titles + paths
  → two look relevant

summary(q="SWAT calibration uncertainty", limit=2)
  → abstract + DOI + citation counts for those two

detail(path="papers/hydrology/ensemble-calibration-2021/paper.md")
  → full text with equations
```

The `budget` parameter on `summary` and `detail` limits output tokens:

```
summary(q="...", budget=1000)   # truncates output to ~1000 tokens
detail(path="...", budget=2000) # truncates content to ~2000 tokens
```

## `watch` — surface KB entries for a source file

Parses a source file (imports, class/function names, docstrings) and searches the KB for matching content.

```bash
papermind --kb ~/Documents/KnowledgeBase watch src/model/groundwater.py
papermind --kb ~/Documents/KnowledgeBase watch src/calibration/optimizer.py --limit 3
```

Also available as the `watch_file` MCP tool, so Claude Code can call it automatically when opening a file.

## `brief --diff` — post-commit knowledge surfacing

Reads a git diff, extracts concepts from changed lines, searches the KB, and surfaces relevant papers. Also checks for pitfall warnings.

```bash
# After a commit
papermind --kb ~/Documents/KnowledgeBase brief --diff HEAD~1..HEAD --repo ~/src/myproject

# Compare feature branch to main
papermind --kb ~/Documents/KnowledgeBase brief --diff main..feature --repo ~/src/myproject
```

```
# brief: HEAD~1..HEAD → 3 match(es)

WARNING: SWAT+ CN has two code paths (daily vs sub-daily) [paper-swat-cn-2019]

1. [14.2] Curve Number rainfall-runoff model review — papers/hydrology/cn-review-2020/paper.md
2. [11.8] SWAT+ parameter sensitivity analysis — papers/hydrology/swat-sensitivity-2021/paper.md
3. [8.1]  Green-Ampt infiltration in continuous simulation — papers/hydrology/green-ampt-2018/paper.md
```

## `chat` — RAG Q&A with a local LLM

Requires [ollama](https://ollama.ai) running locally. Builds a KB context pack and sends it with your question to the specified model.

```bash
ollama serve  # start ollama if not running

papermind --kb ~/Documents/KnowledgeBase chat \
    "How does SWAT+ handle groundwater recharge?" \
    --topic hydrology \
    --model llama3
```

Options: `--topic` filters context, `--max-context` controls KB token budget (default 4000), `--model` selects the ollama model (default `llama3`).

## `context-pack` — session preambles

Generate a briefing to paste into `CLAUDE.md` or load at session start:

```bash
papermind --kb ~/Documents/KnowledgeBase context-pack hydrology \
    --max-tokens 2000 \
    -o docs/kb-briefing.md
```

Then reference it in `CLAUDE.md`:

```markdown
@docs/kb-briefing.md
```

Papers are sorted by citation richness (most-connected first) and truncated to fit the token budget.
