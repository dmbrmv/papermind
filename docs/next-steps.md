# PaperMind — Next Steps

## Completed in v1.0.0 (2026-03-16)

- [x] Unpaywall DOI→PDF resolver
- [x] Deduplicate _try_qmd_reindex
- [x] Path traversal guard on remove (is_relative_to)
- [x] DOI regex tightened
- [x] Clean empty directories after remove
- [x] Package re-ingestion cleanup
- [x] --topic filter in search
- [x] Suppress transformers warnings
- [x] OpenAlex abstract fetching
- [x] fetch --dry-run
- [x] catalog show --json
- [x] BibTeX export
- [x] Title similarity dedup
- [x] Shared _resolve_kb helper
- [x] Config validation (unknown sections, ocr_dpi bounds)
- [x] Consistent CLI error handling
- [x] Download command aligned with fetch (OpenAlex + Unpaywall)
- [x] Shared build_providers()
- [x] transformers dep fixed (>=4.48 with runtime check)
- [x] qmd_search cwd fix
- [x] Codebase re-ingestion dedup guard

## Remaining for v1.1

- CC skill with WebSearch fallback for PDF URLs
- `fetch --dry-run` with richer table (abstract preview, citation count)
- Abstracts in search results (currently only in discovery)
- Paper cross-referencing (which papers cite each other)
- `catalog show --topic <name>` filter
- Progress bars for OCR (per-page) and batch download
- CI/CD (GitHub Actions: pytest + ruff)
- PyPI publish
