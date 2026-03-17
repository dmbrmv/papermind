# Getting Started

Five minutes to a working knowledge base.

## 1. Install

Minimum install (no PDF support):

```bash
pip install papermind
```

With PDF ingestion (requires GPU, uses GLM-OCR):

```bash
pip install "papermind[ocr]"
```

With semantic search (BM25 + vector + LLM reranking):

```bash
pip install papermind
npm install -g @tobilu/qmd
qmd collection add ~/Documents/KnowledgeBase --name my-kb
```

Without qmd, search falls back to grep — still usable, just less ranked.

Check that your environment is ready:

```bash
papermind doctor
```

## 2. Initialize a KB

```bash
papermind --kb ~/Documents/KnowledgeBase init
```

This creates:

```
~/Documents/KnowledgeBase/
  .papermind/
    config.toml
  catalog.json
  catalog.md
  papers/
  packages/
  codebases/
  pdfs/
```

## 3. Fetch your first papers

```bash
papermind --kb ~/Documents/KnowledgeBase fetch "SWAT+ calibration machine learning" -n 5 -t hydrology
```

Expected output (abbreviated):

```
Searching for: SWAT+ calibration machine learning (limit=5)
Found 12 result(s)
  OK   Deep learning surrogate for SWAT+ calibration
  OK   Hybrid ML-SWAT streamflow prediction
  SKIP A calibration framework for SWAT... — no PDF URL
  ...
3 paper(s) ingested into topic 'hydrology'
```

Only open-access papers with PDF URLs are downloaded. Duplicates are skipped automatically.

## 4. Search

```bash
papermind --kb ~/Documents/KnowledgeBase search "evapotranspiration"
```

If qmd is installed, this uses semantic search. Otherwise it falls back to grep across all `.md` files.

## 5. Check what's in the KB

```bash
papermind --kb ~/Documents/KnowledgeBase catalog show
papermind --kb ~/Documents/KnowledgeBase catalog stats
```

## Configure API keys (optional but recommended)

Set environment variables to enable additional discovery sources:

```bash
export PAPERMIND_SEMANTIC_SCHOLAR_KEY=your_key
export PAPERMIND_EXA_KEY=your_key
```

Or add them to `~/Documents/KnowledgeBase/.papermind/config.toml`:

```toml
[apis]
semantic_scholar_key = "your_key"
exa_key = "your_key"
```

Without keys, OpenAlex is used (no key required, lower rate limits).

## Run offline

```bash
papermind --kb ~/Documents/KnowledgeBase --offline search "calibration uncertainty"
```

All network calls are disabled. Useful when working without internet access.
