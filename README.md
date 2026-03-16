# PaperMind

Scientific knowledge base: papers, packages, and codebases → queryable markdown.

[![PyPI](https://img.shields.io/pypi/v/papermind)](https://pypi.org/project/papermind/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

PaperMind ingests heterogeneous scientific sources — PDFs, PyPI packages, and source trees — into a portable, plain-text knowledge base. A CLI manages ingestion, search, and discovery. An MCP server exposes the KB as tools to any AI assistant that speaks the Model Context Protocol.

---

## Installation

**Minimum (no PDF support):**

```bash
pip install papermind
```

**With PDF ingestion (GLM-OCR — requires GPU):**

```bash
pip install "papermind[ocr]"
```

> GLM-OCR requires a recent transformers build. If you get a model loading error:
> `pip install "transformers @ git+https://github.com/huggingface/transformers.git"`

**With semantic search (qmd):**

```bash
npm install -g @tobilu/qmd
qmd collection add ~/kb --name my-kb
```

**With browser-based package docs:**

```bash
pip install "papermind[browser]"
playwright install chromium
```

---

## Quick Start

```bash
# Initialize a knowledge base
papermind --kb ~/kb init

# Fetch papers: search + download + OCR + ingest in one step
papermind --kb ~/kb fetch "SWAT+ calibration machine learning" -n 10 -t swat_ml

# Search
papermind --kb ~/kb search "evapotranspiration calibration"

# Ingest a local PDF
papermind --kb ~/kb ingest paper path/to/paper.pdf --topic hydrology

# Ingest a Python package's API docs
papermind --kb ~/kb ingest package numpy

# Ingest a source tree
papermind --kb ~/kb ingest codebase ~/src/myproject --name myproject

# Check what's in the KB
papermind --kb ~/kb catalog show
```

---

## Command Reference

All commands accept `--kb <path>` as a global option. Pass `--offline` to disable all network access.

### Top-level commands

| Command | Description |
|---------|-------------|
| `init` | Initialize a new knowledge base directory |
| `fetch <query>` | Search, download, and ingest papers in one step |
| `search <query>` | Search the KB (semantic via qmd, or grep fallback) |
| `discover <query>` | Find papers via OpenAlex / Semantic Scholar / Exa |
| `download <url\|doi>` | Download a paper PDF by URL or DOI |
| `crawl <id>` | Follow citation DOIs from a seed paper to build a connected KB |
| `related <id>` | Show papers in the KB connected by citations |
| `backfill` | Enrich existing papers with citation data from Semantic Scholar |
| `context-pack` | Generate a compressed topic briefing for agent context injection |
| `watch <file>` | Surface relevant KB entries for a source code file |
| `export-bibtex` | Export paper citations as BibTeX |
| `migrate` | Convert legacy flat layout to per-paper subdirectories |
| `reindex` | Rebuild `catalog.json` and `catalog.md` from the filesystem |
| `remove <id>` | Remove an entry and its files from the KB |
| `doctor` | Check installed dependencies and tool availability |
| `serve` | Start the MCP server (stdio transport) |
| `version` | Print version |

### Sub-commands

| Command | Description |
|---------|-------------|
| `ingest paper <path>` | Ingest a PDF (or folder of PDFs) via GLM-OCR |
| `ingest package <name>` | Extract a PyPI package's API and documentation |
| `ingest codebase <path>` | Walk a source tree (Python, Fortran, C, Rust) |
| `catalog show` | List all KB entries (`--json` for machine-readable, `--topic` to filter) |
| `catalog stats` | Summary statistics by type and topic |
| `audit stale` | List entries not verified recently |
| `audit verify <id>` | Mark a paper as verified today |
| `audit check-versions` | Check if indexed packages have newer versions on PyPI |
| `equations show <id>` | Show equations extracted from a paper |
| `equations backfill` | Extract equations for all papers and store in frontmatter |
| `tags refresh` | Recompute TF-IDF tags for all papers |

### Examples

```bash
# Fetch until 10 new papers are ingested (multi-round, dedup-aware)
papermind --kb ~/kb fetch "differentiable hydrology neural ODE" --target 10 -t diff_hydro

# Preview discovery without downloading
papermind --kb ~/kb fetch "SWAT calibration" -n 5 --dry-run

# Crawl citation graph from a seed paper (outward + inward)
papermind --kb ~/kb crawl my-paper-id --direction both --depth 2

# Inject a topic briefing into agent context
papermind --kb ~/kb context-pack --topic swat_ml --max-tokens 2000

# Surface KB knowledge for a source file
papermind --kb ~/kb watch src/model.py

# Search with topic and year filters
papermind --kb ~/kb search "groundwater recharge" --topic hydrology --year 2020

# Run fully offline
papermind --kb ~/kb --offline search "calibration uncertainty"
```

---

## MCP Server

PaperMind exposes your KB to AI assistants via the [Model Context Protocol](https://modelcontextprotocol.io/).

**Claude Code (`.claude/mcp.json`):**

```json
{
  "mcpServers": {
    "papermind": {
      "command": "papermind",
      "args": ["--kb", "/path/to/kb", "serve"]
    }
  }
}
```

**Available MCP tools (tiered retrieval):**

| Tool | Tier | Description |
|------|------|-------------|
| `scan` | 1 | Titles + IDs + scores (~50 tokens/result). Start here. |
| `summary` | 2 | Structured abstract + metadata (~500 tokens/result) |
| `detail` | 3 | Full document content with budget control |
| `get` | — | Read a single document by path |
| `multi_get` | — | Read multiple documents in one call |
| `catalog_stats` | — | KB statistics by type and topic |
| `list_topics` | — | All topics in the KB |
| `discover_papers` | — | Search academic APIs without ingesting |
| `watch_file` | — | Surface relevant KB entries for a source file |

The tiered design keeps token cost low: use `scan` to identify candidates, `summary` to qualify, `detail` only when full text is needed.

---

## KB Structure

Each knowledge base is a directory with this layout:

```
~/kb/
  .papermind/
    config.toml          # KB configuration
  catalog.json           # Machine-readable index
  catalog.md             # Human-readable index
  papers/
    <slug>/
      paper.md           # OCR output (markdown + LaTeX equations)
      original.pdf       # Source PDF
      images/            # Figures extracted from PDF
  packages/
    <name>/
      <name>.md          # Package API documentation
  codebases/
    <name>/
      <name>.md          # Extracted source summary
  pdfs/                  # Staging area for downloads
```

Paper frontmatter carries structured metadata: title, DOI, authors, year, topic, tags, abstract, citation graph (`cites` / `cited_by`), extracted equations, and freshness tracking fields.

---

## Key Features

- **Discovery**: parallel search across OpenAlex, Semantic Scholar, and Exa; ranked by citation count, DOI presence, and PDF availability
- **OCR**: local GPU-based PDF conversion via GLM-OCR (0.9B params, MIT license, LaTeX equation output)
- **Citation graph**: `cites` / `cited_by` from Semantic Scholar stored in frontmatter; `crawl` follows DOIs to expand the KB automatically
- **Equation extraction**: regex-based `$$`/`$` block extraction with section context; stored in frontmatter for MCP retrieval
- **Auto-tagging**: TF-IDF keyword extraction across the KB; alias expansion via `aliases.yaml` with domain cluster support
- **Watch**: AST concept extraction from source files → KB search; available as both CLI command and MCP tool
- **Tiered MCP**: three retrieval tiers (scan/summary/detail) to control token budget; `budget` parameter for fine-grained control
- **Freshness tracking**: `audit stale` / `audit verify` / `audit check-versions` for KB maintenance
- **Search**: hybrid semantic search via qmd (BM25 + vector + LLM reranking) with grep fallback and `--year` / `--topic` filters

---

## Configuration

Each KB has a `.papermind/config.toml`. All keys are optional.

```toml
[search]
qmd_path = "qmd"
fallback_search = true

[apis]
semantic_scholar_key = ""
exa_key = ""

[ingestion]
ocr_model = "zai-org/GLM-OCR"
ocr_dpi = 150
default_paper_topic = "uncategorized"

[firecrawl]
api_key = ""

[privacy]
offline_only = false
```

**Environment variables** override config file values:

| Variable | Purpose |
|----------|---------|
| `PAPERMIND_EXA_KEY` | Exa search API key |
| `PAPERMIND_SEMANTIC_SCHOLAR_KEY` | Semantic Scholar API key |
| `PAPERMIND_FIRECRAWL_KEY` | Firecrawl API key |
| `HF_TOKEN` | HuggingFace token (faster model downloads) |

---

## Version History

| Version | Date | Highlights |
|---------|------|-----------|
| v1.0.0 | 2026-03-16 | Initial release: OpenAlex/SemanticScholar/Exa discovery, Unpaywall DOI resolver, BibTeX export, dedup, config validation |
| v1.1.0 | 2026-03-16 | GLM-OCR PDF ingestion (local GPU), image extraction, abstract frontmatter |
| v1.2.0 | 2026-03-16 | Citation graph (cites/cited_by), `related` command, Unpaywall enrichment in orchestrator |
| v1.3.0 | 2026-03-16 | PyPI publish workflow, `catalog show --topic` filter, richer dry-run table |
| v1.3.1 | 2026-03-16 | Per-paper subdirectories, `migrate` command, `--target N` flag for guaranteed paper count |
| v1.4.0 | 2026-03-16 | Tiered MCP (scan/summary/detail), `context-pack`, `crawl`, `tags refresh`, freshness audit, `--year` filter |
| v1.5.0 | 2026-03-17 | `watch` command + MCP tool, structured equation extraction, search alias expansion, 426 tests |

---

## Contributing

```bash
git clone https://github.com/dmbrmv/papermind
cd papermind
pip install -e ".[dev]"
uv run pytest tests/ -v
uv run ruff check src/
```

The test suite is fully offline — no network calls, no external tools required.

---

## License

MIT — see [LICENSE](LICENSE).

Third-party dependency licenses: [LICENSE_THIRD_PARTY.md](LICENSE_THIRD_PARTY.md).
