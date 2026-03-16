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

## v1.5 — Proactive Knowledge

PaperMind surfaces knowledge without being asked. Designed for AI agents that
process code and text simultaneously.

- [ ] **`papermind watch <file>`** — given a code file, return relevant KB entries.
  Hook integration: agent opens calibration code → PaperMind surfaces calibration
  papers. Minimal output (~50 tokens) so it doesn't flood context.
- [ ] **Concept ontology** — `concepts.yaml` maps terms to concept clusters
  (gwet_coef → {groundwater, evapotranspiration, capillary_rise}). Enables
  conceptual search beyond keyword matching. `papermind concepts suggest` auto-
  generates from KB content.
- [ ] **Structured equation extraction** — extract LaTeX blocks tagged by equation
  number + symbol table from papers. `search --equations "infiltration rate"`
  returns structured math, not OCR soup. Even partial extraction (regex-based
  LaTeX block detection) is high value.
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

- [ ] **Code-to-paper provenance** — `# REF: doi:10.1029/... eq.7` annotations
  in code that PaperMind indexes. `papermind provenance <file>` returns the papers
  that justify each equation. Bidirectional: paper → code implementations, code →
  source papers.
- [ ] **Equation-to-code mapping** — given a paper equation and a code function,
  propose symbol → variable mapping with confidence scores. Flag discrepancies
  (missing terms, wrong exponents, unit mismatches).
- [ ] **Implementation verification** — `papermind verify --paper <id> --eq 4.2.1
  --code <file>::<function>`. Line-by-line alignment of paper equation vs code
  implementation. Unit consistency checking.
- [ ] **Two MCP servers** — split into `papermind-retrieval` (5 tools, always on)
  and `papermind-analysis` (deferred, on-demand) to keep tool surface lean.
- [ ] **Agent memory integration** — `kb:entry-id` references in MEMORY.md files.
  `papermind resolve` MCP tool expands references. `papermind sync-memory` validates
  and suggests references.
- [ ] **Project profile** — auto-generated from codebase (imports, docstrings, config).
  Drives search relevance, proactive suggestions, and ingestion priorities.
- [ ] **Research sessions** — shared scratchpad for multi-agent workflows.
  Lead agent creates session, sub-agents contribute findings, any agent reads
  accumulated results.
- [ ] **API version diffing** — `papermind api-diff pandas 2.1 3.0 DataFrame.to_parquet`.
  Track breaking changes across package versions.

## v3.0 — Platform (future)

- Web UI for browsing and searching the KB
- Collaborative KBs (multi-user, shared collections)
- Recommendation engine (suggest papers based on reading history)
- REST API for programmatic access beyond MCP
