# HydroFound — Next Steps

Planned improvements after v0.1.0 E2E validation (2026-03-16).

## Priority 1: PDF Download Hit Rate

**Problem**: Only ~5/28 results yield actual PDFs. Most URLs are HTML landing pages.

### 1a. Unpaywall integration
- Free API, no key needed (just email)
- Given a DOI, returns direct PDF URL for open-access papers
- Chain: OpenAlex finds papers with DOIs → Unpaywall resolves DOI → direct PDF
- Expected to boost hit rate from ~18% to ~50%+
- **Implementation**: new `discovery/unpaywall.py`, called in `fetch` command after download fails

### 1b. CC skill with WebSearch
- Claude Code's `WebSearch` tool can search `"<title> filetype:pdf"`
- Add to the hydrofound CC skill as a fallback when API providers don't have PDF URLs
- Only works inside Claude Code sessions, not standalone CLI

## Priority 2: Code Quality Cleanup

### 2a. Deduplicate `_try_qmd_reindex`
- Three copies: `paper.py`, `cli/ingest.py`, `query/qmd.py`
- Consolidate into `query/qmd.py` only

### 2b. Path traversal guard on `remove`
- MCP server has resolve+startswith check, CLI `remove` doesn't
- Add same guard before `unlink()`

### 2c. DOI regex tighten
- Current: `(10\.\d{4,9}/[^\s]+)` — captures brackets, pipes
- Fix: `(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)`

### 2d. Clean empty directories after remove
- `remove` deletes files but leaves empty `codebases/<name>/` dirs

### 2e. Package re-ingestion cleanup
- Delete old package directory before writing new files

## Priority 3: UX Polish

### 3a. `--topic` filter in search
- `fallback_search` supports it, CLI doesn't expose it
- Add `--topic` option to `search` command

### 3b. `fetch` progress bar
- Show per-paper progress during OCR (page X/Y)
- Rich progress bar for download + ingestion

### 3c. Suppress transformers warnings
- `use_fast` warning, `unauthenticated requests` warning
- Set `HF_HUB_DISABLE_PROGRESS_BARS=1` and configure logging

## Priority 4: Publishing

### 4a. Push to GitHub
- Create repo, push main branch
- Update README with actual install instructions (transformers dev branch requirement)
- Add CI (GitHub Actions: pytest + ruff)

### 4b. Re-tag v0.2.0
- v0.1.0 was pre-GLM-OCR, pre-OpenAlex
- Tag new version after Priority 1-2 are done

### 4c. PyPI publish
- After CI is green and README is accurate
- `uv build && uv publish`
