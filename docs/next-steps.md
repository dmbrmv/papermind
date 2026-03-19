# PaperMind — Roadmap

## Shipped

### v1.0.0 (2026-03-16)
- Unpaywall DOI→PDF resolver
- Path traversal protection, DOI regex tightening
- Title similarity dedup, codebase re-ingestion dedup guard
- OpenAlex abstract fetching, `fetch --dry-run`, `catalog show --json`
- BibTeX export, `--topic` filter in search
- Config validation (unknown sections, ocr_dpi bounds)
- Consistent CLI error handling, shared `_resolve_kb` + `build_providers()`
- transformers dep fix (>=4.48 with runtime check), qmd_search cwd fix

### v1.1.0 (2026-03-16)
- GLM-OCR PDF converter (0.9B, MIT, local GPU)
- Image extraction from PDFs
- Abstract storage in frontmatter
- Rich progress bar for OCR
- GitHub Actions CI (pytest + ruff, Python 3.11+3.12)

### v1.2.0 (2026-03-16)
- Unpaywall enrichment in orchestrator (all results pre-populated)
- Discovery result ranking by quality signals (DOI, pdf_url, academic domain)
- Citation graph: cites/cited_by from Semantic Scholar in frontmatter
- `papermind related` command for connected papers
- CC skill renamed hydrofound → papermind with WebSearch fallback

### v1.3.0 (2026-03-16)
- PyPI publish workflow (GitHub Actions, OIDC trusted publisher)
- `catalog show --topic <name>` filter
- Richer `fetch --dry-run` table (abstract, citation count, quality score)
- Abstracts in grep fallback search results

### v1.3.1 (2026-03-16)
- `--target N` flag for guaranteed new paper count per session
- Per-paper subdirectories (slug/paper.md + original.pdf + images/)
- `papermind migrate` command for legacy KB conversion
- `--from-git` and `--source-path` for package ingestion
- Code review fixes (7 issues: merge cites/cited_by, type annotations,
  migrate regex, MCP topic passthrough, catalog.md skip, max_rounds, None guard)

---

### v1.4.0 (2026-03-16)
- Tiered MCP retrieval (scan/summary/detail + budget parameter)
- `context-pack` command for agent context injection
- Citation crawl with OA-aware DOI filtering (OpenAlex batch check)
- Citation backfill via Semantic Scholar detail endpoint
- `--year` filter for search (from year onward)
- Auto-tagging via TF-IDF keyword extraction (`papermind tags refresh`)
- Freshness tracking (`audit stale`, `audit verify`, `audit check-versions`)
- `--from-git` and `--source-path` for package ingestion
- Code review fixes (7 issues from 3-agent parallel review)
- OpenAlex DOI→PDF fallback for crawl

### Deferred to v1.5+
- Playwright download fallback (JS-rendered PDFs from paywalled sites)

### v1.5.0 (2026-03-17)
- `papermind watch <file>` — AST concept extraction → KB search (CLI + MCP tool)
- Structured equation extraction — regex `$$`/`$` blocks, section context, backfill
- Search alias expansion — `aliases.yaml` with 12 domain clusters
- 60 new tests for all v1.5 features (366 → 426 tests)

### Deferred — concept ontology
Premature at <75 papers. Simple alias file used instead. Revisit at 75+ papers.

## v1.6 — Deeper Proactive Knowledge

- [ ] **Structured table extraction** — parameter tables from papers as queryable
  data (parameter name, min, max, units, catchment type, reference). Highest-value
  extraction target for hydrology KBs.
- [ ] **Anti-pattern warnings** — entries can have `pitfalls` field with pattern +
  warning. Agent touching matching code gets warned proactively.
- [ ] **Commit-triggered briefing** — `papermind brief --diff HEAD~1..HEAD` surfaces
  relevant knowledge after code changes.
- [ ] **Cross-references** — infer paper relationships beyond citation graph:
  shared keywords, same authors, overlapping methods.
- [ ] **Collection reports** — generate a topic overview: key papers, methods,
  open questions. Literature review bootstrapping.

## v2.0 — Verification & Code-Paper Bridge

The transformative features. PaperMind becomes the link between scientific
literature and scientific code.

- [x] **Code-to-paper provenance** — `# REF: doi:10.1029/... eq.7` annotations
  in code that PaperMind indexes. `papermind provenance show|scan|suggest`.
  Multi-language (Python/Fortran/C). MCP tool: `provenance`.
- [x] **Equation-to-code mapping** — heuristic symbol matcher (exact, normalized,
  glossary, fuzzy). `papermind equation-map <file>::<fn> -e "LaTeX"`. MCP tool: `equation_map`.
- [x] **Implementation verification** — `papermind verify <file>::<fn> --paper <id> --eq N`.
  Coverage score, confidence, verdict (good/partial/poor). MCP tool: `verify_implementation`.
- [ ] **Two MCP servers** — split into `papermind-retrieval` and `papermind-analysis`.
  *Deferred — 19 tools is manageable; split at 25+.*
- [x] **Agent memory integration** — `kb:paper-id` and `kb:doi:10.xxx` references.
  `papermind resolve`, `papermind validate-refs`. MCP tool: `resolve_refs`.
- [x] **Project profile** — auto-generated from codebase (walk + provenance scan).
  Languages, functions, classes, linked papers, inferred topics. MCP tool: `project_profile`.
- [x] **Research sessions** — `papermind session create|add|read|list|close`.
  Tag-filtered, append-only scratchpad. MCP tools: session_create/add/read.
- [x] **API version diffing** — `papermind api-diff <old> <new> [-f function]`.
  Detects added/removed/changed functions with parameter-level detail.

## v3.0 — Platform (future)

- Web UI for browsing and searching the KB
- Collaborative KBs (multi-user, shared collections)
- Recommendation engine (suggest papers based on reading history)
- REST API for programmatic access beyond MCP
