# PaperMind MCP Server Setup

## Install

```bash
pip install papermind
papermind init ~/Documents/KnowledgeBase
```

## Ingest Content

```bash
# Ingest a PDF paper
papermind --kb ~/Documents/KnowledgeBase ingest paper paper.pdf --topic hydrology

# Ingest a markdown file (e.g., from Obsidian)
papermind --kb ~/Documents/KnowledgeBase ingest paper notes.md --topic hydrology

# Batch ingest a folder of papers (PDF + markdown)
papermind --kb ~/Documents/KnowledgeBase ingest paper ~/papers/ --topic climate

# Ingest a Python package API
papermind --kb ~/Documents/KnowledgeBase ingest package numpy

# Ingest a codebase
papermind --kb ~/Documents/KnowledgeBase ingest codebase ~/project --name myproject
```

## Configure MCP Client

**Claude Code** (`~/.claude.json` or project `.mcp.json`):
```json
{
  "mcpServers": {
    "papermind": {
      "command": "papermind",
      "args": ["--kb", "/path/to/KnowledgeBase", "serve"]
    }
  }
}
```

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "papermind": {
      "command": "papermind",
      "args": ["--kb", "/path/to/KnowledgeBase", "serve"]
    }
  }
}
```

## Tools

### scan
Fast triage: titles, scores. ~50 tokens/result.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | yes | Search query |
| `scope` | string | no | `papers`, `packages`, `codebases` |
| `topic` | string | no | Filter by topic |
| `year_from` | int | no | Papers from this year onward |
| `limit` | int | no | Max results (default: 20) |

### summary
Abstracts + metadata. ~500 tokens/result.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | yes | Search query |
| `scope` | string | no | Content type filter |
| `topic` | string | no | Topic filter |
| `limit` | int | no | Max results (default: 5) |
| `budget` | int | no | Token budget (approximate) |

### detail
Full document content. ~3000 tokens/result.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | yes | Relative path from scan/summary |
| `budget` | int | no | Token budget (approximate) |

### get
Read document by path. No search.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | yes | Relative path within KB |

### multi_get
Batch-read documents.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `paths` | string[] | yes | List of relative paths |

### catalog_stats
KB overview. No parameters.

### list_topics
Available topics. No parameters.

### discover_papers
Search academic APIs for new papers.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | yes | Search query |
| `limit` | int | no | Max results (default: 10) |
| `source` | string | no | `all`, `semantic_scholar`, `exa` |

### watch_file
Surface relevant KB entries for source code.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `file_path` | string | yes | Absolute path to source file |
| `limit` | int | no | Max results (default: 5) |

## Troubleshooting

- **No results**: Check `papermind --kb <path> catalog stats` to verify KB has content
- **MCP not connecting**: Verify the KB path exists and contains `.papermind/` directory
- **Slow first search**: Normal if using qmd — models need to load (~3 GB)
- **Missing papers**: Run `papermind --kb <path> reindex` to rebuild the catalog
