# Changelog

## v3.1.0 (2026-03-19)

### Added
- **SQLite backend** — WAL-mode database for catalog and sessions
- **Web UI** — browser-based KB explorer at / (dark academic theme)
- **KB export/import** — portable `.pmkb` archives with DOI dedup
- **Reference tools** — `cite`, `bib-gap`, `respond` for scientific writing
  - `papermind cite "claim"` — find papers supporting a claim (KB + OpenAlex)
  - `papermind bib-gap <draft>` — find uncited claims in a paper draft
  - `papermind respond "comment"` — find evidence for reviewer responses
- **MCP tools**: find_references, bib_gap_analysis (21 total)
- **API endpoints**: POST /analysis/cite, POST /analysis/bib-gap
- **CLAUDE.md** — AI agent instructions for the repo

### Changed
- MCP server split: 791-line monolith → 68-line dispatcher + separate
  schemas and handlers modules
- Search results enriched with catalog metadata (real paper titles)
- crossref uses CatalogIndex instead of filesystem scan (O(N²) → O(1))
- Session CRUD routes through SQLite when available
- Shared `query/dispatch.py` eliminates search code duplication

### Fixed
- Zip path traversal vulnerability in import
- CORS wildcard + credentials (invalid spec combo)
- Batch DB commits (N per-row commits → 1 transaction)
- Catalog read operations use in-memory cache (no DB re-open)
- `_ENTRY_FIELDS` module constant (4x introspection → 1)
- Silent swallowing of session migration errors (now logged)

## v3.0.0 (2026-03-19)

### Added
- **REST API** — FastAPI with 15 HTTP endpoints
- OpenAPI docs at /docs
- `papermind serve --http [--port 8080]`
- Optional `[api]` extra (fastapi + uvicorn)

## v2.0.0 (2026-03-19)

### Added
- **Code-to-paper provenance** — `# REF:` annotations (Python/Fortran/C)
- **Equation-to-code mapping** — heuristic symbol matcher
- **Implementation verification** — coverage + confidence scoring
- **Project profile** — codebase summary generation
- **Agent memory** — `kb:paper-id` references in markdown
- **Research sessions** — append-only scratchpad
- **API version diffing** — package API comparison
- 19 MCP tools, 571 tests

## v1.7.0 (2026-03-19)

### Added
- **Markdown ingestion** — `.md`/`.markdown` files, Obsidian-compatible
- **`papermind explain`** — parameter glossary (20 entries) + KB search
- **`papermind report`** — topic overview generation
- **`papermind crossref`** — keyword-based paper relationships
- **Claude Code skill** — `skills/papermind/SKILL.md`
- qmd semantic search backend fixed (65 files embedded)

## v1.6.0 (2026-03-17)

- Table extraction, pitfalls, `brief --diff`
- Semantic Scholar removed (OpenAlex-only)

## v1.5.0 (2026-03-17)

- `watch` command + MCP tool
- Equation extraction, search aliases
- 426 tests

## v1.0.0–v1.4.0 (2026-03-16)

- Core platform: discovery, OCR, search, MCP, citation graph
- PyPI publish, tiered retrieval, auto-tagging, freshness audit
