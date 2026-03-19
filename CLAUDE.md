# PaperMind — AI Agent Instructions

## Project

Scientific knowledge base: papers, packages, codebases → queryable
markdown. CLI + MCP server + REST API + Web UI.

**Stack**: Python 3.11+ / uv / Typer CLI / FastAPI / SQLite / qmd

## Environment

```bash
uv sync --extra dev --extra api     # development + API
uv sync --extra ocr                 # PDF ingestion (GPU)
uv sync --extra browser             # Playwright tests
```

**Test runner**: `uv run python -m pytest tests/ -q` (NOT `uv run pytest`)

**Lint + format**: `uv run ruff check .` and `uv run ruff format .`

**KB path**: `~/Documents/KnowledgeBase` (50+ papers, 3 packages, 2 codebases)

## Architecture

```
src/papermind/
    api/              # FastAPI REST API (routes/, schemas, deps)
    catalog/          # CatalogIndex — SQLite + JSON dual backend
    cli/              # Typer CLI commands (55+)
    discovery/        # Paper search (OpenAlex, Exa)
    ingestion/        # PDF/markdown/package/codebase ingestion
    mcp_tools/        # MCP tool schemas + handlers (21 tools)
    query/            # Search dispatch (qmd semantic + grep fallback)
    static/           # Web UI (index.html, served at /)
    # Domain modules:
    api_diff.py       # Package API version comparison
    crossref.py       # Keyword-based paper relationships
    db.py             # SQLite backend (WAL mode)
    equation_map.py   # LaTeX symbol → code variable matching
    explain.py        # Parameter glossary + KB search
    glossary.yaml     # Curated parameter definitions (20 entries)
    memory.py         # kb:paper-id reference parsing
    profile.py        # Codebase summary generation
    provenance.py     # # REF: annotation parsing
    references.py     # Claim → reference finding (KB + external)
    report.py         # Topic overview reports
    session.py        # Research sessions (SQLite + JSON fallback)
    sharing.py        # KB export/import (.pmkb archives)
    verify.py         # Code vs paper equation verification
    watch.py          # Source file → KB paper surfacing
```

## Conventions

- **Line length**: 88 (ruff default)
- **Imports**: absolute from `papermind`, lazy imports in handlers
- **Frontmatter**: markdown files use python-frontmatter (YAML)
- **Storage truth**: markdown frontmatter is authoritative;
  SQLite and catalog.json are derived caches
- **Search**: qmd (semantic + BM25) → grep fallback. Use
  `papermind.query.dispatch.run_search()` — never duplicate
- **CatalogIndex**: reads use in-memory cache (`self.entries`);
  writes go to SQLite + JSON. Never open DB connections for reads.
- **Tests**: pytest, tmp_path fixtures, CliRunner for CLI,
  TestClient for API (requires `[api]` extra)

## Immutable Rules

- **No `/tmp` writes** — use project-local temp files
- **No `innerHTML`** — use DOM APIs (textContent, createElement)
- **Zip extraction must validate paths** — `is_relative_to()` guard
- **CORS**: explicit localhost origins, not `allow_origins=["*"]`
- **DB commits**: via `get_connection()` context manager, not per-row
- **`_ENTRY_FIELDS`**: use the module constant, don't call `fields()`

## Key Gotchas

- ruff format hook strips unused imports on Write/Edit — if adding
  an import and its usage in separate edits, add the usage first
- `pytest.importorskip("fastapi")` in test_api/conftest.py —
  API tests skip gracefully without `[api]` extra
- qmd not available in CI — search tests use grep fallback
- `crossref.py` reads from CatalogIndex, not filesystem
- `session.py` routes through SQLite when `papermind.db` exists
