---
name: papermind
description: Search and retrieve from the PaperMind scientific knowledge base. Use when users ask about papers, want literature context, need parameter guidance, or reference scientific methods.
license: MIT
compatibility: Requires papermind MCP server. Install via `pip install papermind`.
allowed-tools: mcp__papermind__*
---

# PaperMind - Scientific Knowledge Base

Search engine for scientific papers, package APIs, and codebase signatures stored as markdown.

## Status

!`papermind --kb ${PAPERMIND_KB_PATH:-~/Documents/KnowledgeBase} catalog stats 2>/dev/null || echo "Not configured: pip install papermind && papermind init ~/Documents/KnowledgeBase"`

## Tiered Retrieval

PaperMind uses three tiers to control token cost. **Always start at the cheapest tier.**

| Tier | Tool | Tokens/result | Use when |
|------|------|---------------|----------|
| 1 | `scan` | ~50 | Triage — deciding what's relevant |
| 2 | `summary` | ~500 | Qualifying — reading abstracts and metadata |
| 3 | `detail` | ~3000 | Deep read — equations, methods, full text |

### Workflow

```
scan "rainfall-runoff models"           → 20 results, titles + scores
  ├─ pick top 3-5 relevant
  └─ summary "rainfall-runoff models"   → abstracts, DOIs, years
       ├─ pick 1-2 worth full read
       └─ detail path="papers/..."      → complete paper content
```

**Do not jump to `detail` without scanning first** — it wastes tokens and context window.

## MCP Tools

### Search Tools

#### `scan` (tier 1)
Fast triage: titles, IDs, relevance scores.

```json
{
  "q": "SWAT+ calibration sensitivity",
  "scope": "papers",
  "topic": "hydrology",
  "year_from": 2018,
  "limit": 20
}
```

**Parameters:**
- `q` (required) — search query, natural language or keywords
- `scope` — filter: `papers`, `packages`, `codebases`
- `topic` — filter by KB topic
- `year_from` — papers from this year onward
- `limit` — max results (default: 20)

#### `summary` (tier 2)
Structured abstracts with metadata.

```json
{
  "q": "Green-Ampt infiltration",
  "limit": 5,
  "budget": 4000
}
```

**Parameters:** same as `scan`, plus:
- `budget` — max output tokens (approximate). Results truncated to fit.

#### `detail` (tier 3)
Full document: text, equations, figures, references.

```json
{
  "path": "papers/hydrology/green-ampt-model-1911/paper.md",
  "budget": 8000
}
```

**Parameters:**
- `path` (required) — relative path from scan/summary results
- `budget` — max output tokens

### Direct Access

#### `get`
Read a single document by path (raw content, no search).

```json
{ "path": "papers/hydrology/swat-plus-2012/paper.md" }
```

#### `multi_get`
Batch-read multiple documents.

```json
{ "paths": ["papers/hydrology/paper-a/paper.md", "packages/optuna/api.md"] }
```

### Discovery

#### `discover_papers`
Search academic APIs (OpenAlex, Semantic Scholar, Exa) for new papers — not in the KB yet.

```json
{
  "query": "differentiable hydrological modeling",
  "limit": 10,
  "source": "all"
}
```

- `source` — `all`, `semantic_scholar`, `exa`

### Context Tools

#### `catalog_stats`
KB overview: paper/package/codebase counts, topics. No parameters.

#### `list_topics`
Available topic categories. No parameters.

#### `watch_file`
Surface relevant KB entries for a source code file. Extracts concepts (imports, functions, docstrings) and searches the KB.

```json
{
  "file_path": "/home/user/project/src/model/water_balance.py",
  "limit": 5
}
```

### Analysis Tools

#### `explain_concept`
Explain a parameter or concept (glossary first, KB search fallback).

```json
{ "concept": "CN2" }
```

#### `equation_map`
Map LaTeX equation symbols to code variables (heuristic matching).

```json
{
  "equation_latex": "Q = K_s \\cdot S^{0.5}",
  "file_path": "/path/to/model.py",
  "function_name": "calc_runoff"
}
```

#### `provenance`
Extract `# REF:` code-to-paper annotations from a source file.

```json
{ "file_path": "/path/to/water_balance.py" }
```

#### `project_profile`
Generate a codebase summary (languages, functions, linked papers).

```json
{ "codebase_path": "/path/to/project" }
```

#### `verify_implementation`
Check if code implements a paper equation correctly.

```json
{
  "paper_id": "paper-scs-cn-1986",
  "equation_number": "2.1",
  "file_path": "/path/to/model.py",
  "function_name": "calc_runoff"
}
```

#### `resolve_refs`
Resolve `kb:paper-id` references in markdown text.

```json
{ "text": "See kb:paper-green-ampt-1911 for details." }
```

### Session Tools

#### `session_create`
Create a research session for multi-agent collaboration.

```json
{ "name": "baseflow literature review" }
```

#### `session_add`
Add a finding to an open session.

```json
{
  "session_id": "baseflow-literature-review",
  "content": "Found 3 papers on recession analysis",
  "agent": "sub-agent-1",
  "tags": ["key"]
}
```

#### `session_read`
Read accumulated findings (optionally filtered by tag).

```json
{ "session_id": "baseflow-literature-review", "tag": "key" }
```

## Query Patterns

| Goal | Approach |
|------|----------|
| Literature review | `scan` broad query → `summary` top hits → `detail` key papers |
| Parameter guidance | `explain_concept` for known params, `scan` for others |
| Debugging help | `scan` symptom (e.g., "SWAT water balance error") |
| Package API lookup | `scan` with `scope: "packages"` |
| Cross-reference | `detail` a paper → follow DOIs in `cites`/`cited_by` |
| Code context | `watch_file` on the file you're editing |
| Verify implementation | `verify_implementation` with paper + equation + code |
| Multi-agent research | `session_create` → sub-agents `session_add` → `session_read` |

### Scientific Writing Tools

#### `find_references`
Find papers supporting a claim. KB first, OpenAlex fallback.

```json
{
  "claim": "SWAT+ has been widely used for watershed modeling",
  "limit": 5,
  "search_external": true
}
```

#### `bib_gap_analysis`
Analyze a paper draft for claims missing citations.

```json
{
  "file_path": "/path/to/draft.md",
  "search_external": true
}
```

## Writing Good Queries

**Be specific.** "SWAT+ calibration CMA-ES sensitivity" beats "calibration methods".

**Include domain terms.** The KB contains scientific papers — use the vocabulary: "Green-Ampt infiltration", "Muskingum routing", "baseflow separation".

**Scope when possible.** If you know you want papers, set `scope: "papers"`. If you want package docs, set `scope: "packages"`.

## Setup

See [references/mcp-setup.md](references/mcp-setup.md) for installation and configuration.
