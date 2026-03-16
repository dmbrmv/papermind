# Next Session Plan

## Current State
- v1.5.0 on PyPI, 426 tests, 25 papers in KB
- 24 CLI commands, 10 MCP tools
- KB at ~/Documents/KnowledgeBase

## Priority 1: RAG Chat Mode (~1h)

The user wants to use the KB as context for local LLMs. Build:

```bash
papermind chat "How does SWAT+ handle groundwater recharge?"
  --model ollama/llama3:8b    # or any ollama model
  --topic hydrology           # scope context to topic
  --max-context 4000          # token budget for KB context
```

Implementation:
1. `context-pack` already generates the briefing
2. Add `papermind chat` that: generates context-pack → sends to ollama API → streams response
3. Needs `httpx` to call ollama at `localhost:11434/api/generate`
4. Optional: `--provider` flag for openai-compatible APIs

This is ~100 lines. The hard part is prompt engineering — structuring the KB context so the LLM uses it effectively.

## Priority 2: Grow KB to 50+ Papers (~30min)

The KB has 25 papers. More papers = better TF-IDF tags, better search, better context-pack. Target topics:
- `hydrology`: 10 more (SWAT+ applications, ERA5 forcing, soil moisture)
- `ml-methods`: 5 more (transformers for time series, graph networks)
- New topic `remote-sensing`: 5 papers (satellite hydrology, MODIS ET)

## Priority 3: Table Extraction (~1h)

From the roadmap (v1.6). Papers are full of parameter tables that OCR captures as text. Extract them:
- Detect table patterns (markdown `|` tables, or grid-like text)
- Store as structured data in frontmatter
- `papermind tables show <paper-id>` to display
- Most valuable for calibration papers (parameter bounds)

## Priority 4: README Update (~20min)

README.md is stale — doesn't mention v1.2-v1.5 features. Update with:
- Full command reference
- MCP server setup instructions
- Usage examples (fetch, crawl, watch, context-pack)
- KB structure diagram

## Decision Point

Pick based on energy:
- **High energy**: RAG chat + grow KB (most impactful for daily use)
- **Medium energy**: Table extraction + README (polish)
- **Low energy**: Just grow KB + README (minimal code)
