# PaperMind

Scientific knowledge base: papers, packages, and codebases → queryable markdown.

PaperMind ingests heterogeneous scientific sources — PDFs, PyPI packages, and source trees — into a portable, plain-text knowledge base. A CLI manages ingestion, search, and discovery. An MCP server exposes the KB as tools to any AI assistant that speaks the Model Context Protocol.

## Install

**Minimum (no PDF or browser support):**

```bash
pip install papermind
```

**With PDF ingestion (GLM-OCR — requires GPU):**

```bash
pip install "papermind[ocr]"
```

> **Note:** GLM-OCR requires a recent transformers build with GLM-OCR support.
> If `pip install "papermind[ocr]"` gives a model loading error, install the dev branch:
> `pip install "transformers @ git+https://github.com/huggingface/transformers.git"`

**With semantic search (qmd):**

```bash
npm install -g @tobilu/qmd
```

**With browser-based package docs:**

```bash
pip install "papermind[browser]"
playwright install chromium
```

**Requirements:** Python 3.11+, GPU recommended for PDF ingestion

## Quick Start

```bash
# 1. Create a knowledge base
papermind --kb ~/kb init

# 2. Fetch papers (search + download + OCR + ingest in one step)
papermind --kb ~/kb fetch "SWAT+ calibration machine learning" -n 10 -t swat_ml

# 3. Ingest a local PDF
papermind --kb ~/kb ingest paper path/to/paper.pdf --topic hydrology

# 4. Ingest a Python package's API docs
papermind --kb ~/kb ingest package numpy

# 5. Ingest a codebase (Python, Fortran, C, Rust)
papermind --kb ~/kb ingest codebase ~/src/myproject --name myproject

# 6. Search
papermind --kb ~/kb search "evapotranspiration calibration"
papermind --kb ~/kb search "SWAT" --topic swat_ml

# 7. Check what's in the KB
papermind --kb ~/kb catalog show
```

## CLI Reference

All commands take `--kb <path>` as a global option. Pass `--offline` to disable all network access.

| Command | Description |
|---------|-------------|
| `init` | Initialize a new knowledge base directory |
| `fetch <query>` | Search + download + OCR + ingest papers in one step |
| `ingest paper <path>` | Add a paper (PDF) via GLM-OCR |
| `ingest package <name>` | Extract a PyPI package's API and docs |
| `ingest codebase <path>` | Walk a source tree (Python, Fortran, C) |
| `search <query>` | Search the KB (semantic via qmd, or grep fallback) |
| `catalog show` | List all KB entries (`--json` for machine-readable) |
| `catalog stats` | Summary statistics by type and topic |
| `remove <id>` | Remove an entry from the KB |
| `discover <query>` | Find papers via OpenAlex / Semantic Scholar / Exa |
| `download <url\|doi>` | Download a paper PDF |
| `export-bibtex` | Export paper citations as BibTeX |
| `doctor` | Check installed dependencies and tool availability |
| `reindex` | Rebuild `catalog.json` and `catalog.md` from filesystem |
| `serve` | Start the MCP server (stdio transport) |
| `version` | Print version |

### Examples

```bash
# Fetch 10 papers on a topic, auto-download and ingest
papermind --kb ~/kb fetch "differentiable hydrology neural ODE" -n 10 -t diff_hydro

# Preview what fetch would do (no download/ingest)
papermind --kb ~/kb fetch "SWAT calibration" -n 5 --dry-run

# Ingest multiple papers from a directory
papermind --kb ~/kb ingest paper papers/ --topic swat

# Export citations for reference managers
papermind --kb ~/kb export-bibtex > references.bib

# Machine-readable catalog
papermind --kb ~/kb catalog show --json

# Search with topic filter
papermind --kb ~/kb search "calibration" --topic swat_ml

# Run fully offline (no network calls at all)
papermind --kb ~/kb --offline search "groundwater recharge"

# Check tool health
papermind --kb ~/kb doctor
```

## Paper Discovery

PaperMind searches three academic APIs in parallel:

- **[OpenAlex](https://openalex.org/)** — free, no API key, direct PDF URLs for open-access papers
- **[Semantic Scholar](https://www.semanticscholar.org/)** — structured metadata, citation counts (optional API key for higher rate limits)
- **[Exa](https://exa.ai/)** — broad web search (requires API key)
- **[Unpaywall](https://unpaywall.org/)** — DOI→PDF resolver fallback (free, no key)

## PDF OCR

PaperMind uses [GLM-OCR](https://huggingface.co/zai-org/GLM-OCR) (MIT, 0.9B params, #1 OmniDocBench) for PDF→markdown conversion. Features:

- Runs locally on GPU (RTX 3060+ recommended, ~2GB VRAM)
- Outputs structured markdown with LaTeX equations
- Auto-detects section headings (numbered sections, ALL-CAPS)
- Extracts embedded figures as PNG files alongside the markdown
- Source PDF copied next to markdown for easy comparison

Install with `pip install "papermind[ocr]"`. Model downloaded from HuggingFace on first use (~2GB, cached).

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

**Available MCP tools:**

| Tool | Description |
|------|-------------|
| `query` | Search the KB; optional `scope`, `topic`, `limit` |
| `get` | Read a single document by relative path |
| `multi_get` | Read multiple documents in one call |
| `catalog_stats` | KB statistics (counts by type and topic) |
| `list_topics` | All topics in the KB |
| `discover_papers` | Search academic APIs |

## Search

Two search backends:

- **[qmd](https://github.com/tobi/qmd)** — hybrid search (BM25 + vector embeddings + LLM reranking). Install: `npm install -g @tobilu/qmd`, then `qmd collection add ~/kb --name my-kb`
- **Built-in fallback** — grep-based term matching (zero dependencies)

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

## Contributing

```bash
git clone https://github.com/dmbrmv/papermind
cd papermind
pip install -e ".[dev]"
uv run pytest tests/ -v
uv run ruff check src/
```

The test suite is fully offline — no network calls, no external tools required.

## License

MIT — see [LICENSE](LICENSE).

Third-party dependency licenses: [LICENSE_THIRD_PARTY.md](LICENSE_THIRD_PARTY.md).
