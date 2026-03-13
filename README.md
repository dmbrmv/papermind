# HydroFound

Scientific knowledge base: papers, packages, and codebases → queryable markdown.

HydroFound ingests heterogeneous scientific sources — PDFs, PyPI packages, and source trees — into a portable, plain-text knowledge base. A CLI manages ingestion, search, and discovery. An MCP server exposes the KB as tools to any AI assistant that speaks the Model Context Protocol.

## Install

**Minimum (no PDF or browser support):**

```bash
pip install hydrofound
```

**With PDF ingestion (requires [Marker](https://github.com/VikParuchuri/marker) installed separately):**

```bash
pip install hydrofound
pip install marker-pdf          # GPL-3.0 — installed separately to avoid license infection
```

**With browser-based package docs:**

```bash
pip install "hydrofound[browser]"
playwright install chromium
```

**Requirements:** Python 3.11+, optional external tools: `marker` (PDF→MD), `qmd` (semantic search)

## Quick Start

```bash
# 1. Create a knowledge base
hydrofound --kb ~/kb init

# 2. Ingest a paper (PDF or URL)
hydrofound --kb ~/kb ingest paper path/to/paper.pdf --topic hydrology

# 3. Ingest a Python package's API docs
hydrofound --kb ~/kb ingest package numpy

# 4. Ingest a codebase
hydrofound --kb ~/kb ingest codebase ~/src/myproject --name myproject

# 5. Search
hydrofound --kb ~/kb search "evapotranspiration calibration"

# 6. Check what's in the KB
hydrofound --kb ~/kb catalog show
```

## CLI Reference

All commands take `--kb <path>` as a global option. Pass `--offline` to disable all network access.

| Command | Description |
|---------|-------------|
| `init` | Initialize a new knowledge base directory |
| `ingest paper <path\|url>` | Add a paper (PDF, local, or remote URL) |
| `ingest package <name>` | Extract a PyPI package's API and docs |
| `ingest codebase <path>` | Walk a source tree (Python, Fortran, C) |
| `search <query>` | Search the KB (semantic via qmd, or grep fallback) |
| `catalog show` | List all KB entries |
| `catalog stats` | Summary statistics by type and topic |
| `remove <path>` | Remove an entry from the KB |
| `discover <query>` | Find papers via Semantic Scholar / Exa |
| `download <url\|doi>` | Download a paper PDF or HTML |
| `doctor` | Check installed dependencies and tool availability |
| `reindex` | Rebuild `catalog.json` and `catalog.md` from filesystem |
| `serve` | Start the MCP server (stdio transport) |
| `version` | Print version |

### Examples

```bash
# Ingest multiple papers from a directory
hydrofound --kb ~/kb ingest paper papers/ --topic swat

# Discover and immediately download open-access papers
hydrofound --kb ~/kb discover "SWAT+ calibration" --download

# Ingest package with browser (needed for JS-rendered docs)
hydrofound --kb ~/kb ingest package scipy --browser

# Run fully offline (no network calls at all)
hydrofound --kb ~/kb --offline search "groundwater recharge"

# Check tool health
hydrofound --kb ~/kb doctor
```

## MCP Server

HydroFound exposes your KB to AI assistants via the [Model Context Protocol](https://modelcontextprotocol.io/).

**Start the server:**

```bash
hydrofound --kb /path/to/kb serve
```

The server uses stdio transport — configure it in your assistant's MCP client config.

**Claude Desktop (`claude_desktop_config.json`):**

```json
{
  "mcpServers": {
    "hydrofound": {
      "command": "hydrofound",
      "args": ["--kb", "/path/to/kb", "serve"]
    }
  }
}
```

**Claude Code (`.claude/mcp.json`):**

```json
{
  "mcpServers": {
    "hydrofound": {
      "command": "hydrofound",
      "args": ["--kb", "/path/to/kb", "serve"]
    }
  }
}
```

**Available MCP tools:**

| Tool | Description |
|------|-------------|
| `query` | Search the KB; optional `scope` (papers/packages/codebases), `topic`, `limit` |
| `get` | Read a single document by relative path |
| `multi_get` | Read multiple documents in one call |
| `catalog_stats` | KB statistics (counts by type and topic) |
| `list_topics` | All topics in the KB |
| `discover_papers` | Search academic APIs (Semantic Scholar / Exa) |

## Configuration

Each KB has a `.hydrofound/config.toml`. All keys are optional.

```toml
[search]
qmd_path = "qmd"          # path to qmd binary (default: qmd in PATH)
fallback_search = true    # use grep-based fallback when qmd unavailable

[apis]
semantic_scholar_key = "" # optional — higher rate limits
exa_key = ""              # required for Exa discovery

[ingestion]
marker_path = "marker"        # path to marker binary
marker_use_llm = false        # enable LLM-assisted PDF parsing (slower, better)
default_paper_topic = "uncategorized"

[firecrawl]
api_key = ""              # for JS-heavy package docs without Playwright

[privacy]
offline_only = false      # equivalent to passing --offline on every command
```

**Environment variables** override config file values:

| Variable | Purpose |
|----------|---------|
| `HYDROFOUND_EXA_KEY` | Exa search API key |
| `HYDROFOUND_SEMANTIC_SCHOLAR_KEY` | Semantic Scholar API key |
| `HYDROFOUND_FIRECRAWL_KEY` | Firecrawl API key |

## KB Structure

```
~/kb/
├── .hydrofound/
│   └── config.toml
├── papers/
│   └── <topic>/
│       └── <slug>.md       # YAML frontmatter + markdown body
├── packages/
│   └── <name>/
│       └── api.md
├── codebases/
│   └── <name>/
│       └── tree.md
├── catalog.json             # derived cache — rebuilt by `reindex`
└── catalog.md               # human-readable index
```

Markdown files with YAML frontmatter are the source of truth. `catalog.json` is a derived cache and can always be rebuilt with `hydrofound --kb <path> reindex`.

## External Tools

HydroFound calls these as subprocesses (not Python dependencies):

- **[Marker](https://github.com/VikParuchuri/marker)** (GPL-3.0) — PDF to markdown conversion. Called as a subprocess to avoid GPL license propagation to the hydrofound package.
- **[qmd](https://github.com/simonw/qmd)** (optional) — semantic vector search. Falls back to grep-based search when unavailable.

## Contributing

```bash
git clone https://github.com/your-org/hydrofound
cd hydrofound
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/
ruff format src/
```

The test suite is fully offline — no network calls, no external tools required.

## License

MIT — see [LICENSE](LICENSE).

Third-party dependency licenses: [LICENSE_THIRD_PARTY.md](LICENSE_THIRD_PARTY.md).
