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

---

### v1.3.0 (2026-03-16)
- PyPI publish workflow (GitHub Actions, OIDC trusted publisher)
- `catalog show --topic <name>` filter
- Richer `fetch --dry-run` table (abstract, citation count, quality score)
- Abstracts in grep fallback search results
- Progress bars already shipped in v1.1 (OCR) + per-item download status

### Deferred to v1.4+
- Playwright download fallback (JS-rendered PDFs from ScienceDirect, Springer)

## v1.4 — Smarter Ingestion

Make ingested content more useful without requiring external LLMs.

- [ ] **Auto-tagging** — extract keywords from paper text on ingest, populate `tags` field (currently always empty). Start with TF-IDF over corpus, no LLM needed.
- [ ] **Metadata search** — `search --author smith`, `search --year 2023`, `search --doi 10.1/X`. Structured query on frontmatter fields, not just full-text.
- [ ] **Firecrawl integration** — use configured Firecrawl key for package doc rendering (PyPI readme, project URLs, web documentation pages).
- [ ] **Citation enrichment** — for papers already in KB, fetch missing citation metadata from Semantic Scholar (backfill cites/cited_by for papers ingested before v1.2).

## v1.5 — Knowledge Layer

AI-powered features that build on the clean data foundation.

- [ ] **Concept index** — term → papers mapping extracted from titles + abstracts. Enables "show me all papers about evapotranspiration" without full-text search.
- [ ] **LLM summaries** — per-paper 3-sentence summary stored in frontmatter. Run on ingest (optional, requires LLM API key). Surface in catalog and search.
- [ ] **Cross-references** — infer paper relationships beyond citation graph: shared keywords, same authors, overlapping methods. Show in `related` command.
- [ ] **Collection reports** — generate a markdown overview of a topic: key papers, methods used, open questions. Useful for literature review bootstrapping.

## v2.0 — Platform (future)

- Web UI for browsing and searching the KB
- Collaborative KBs (multi-user, shared collections)
- Recommendation engine (suggest papers based on reading history)
- REST API for programmatic access beyond MCP
