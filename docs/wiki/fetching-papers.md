# Fetching Papers

All methods for getting papers into the knowledge base.

## `fetch` — discover, download, and ingest in one step

The main entry point. Searches OpenAlex, Semantic Scholar, and Exa; downloads open-access PDFs; OCRs and ingests them.

```bash
papermind --kb ~/Documents/KnowledgeBase fetch "differentiable hydrology neural ODE" -n 10 -t diff_hydro
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `-n` / `--limit` | 5 | Number of discovery results to attempt |
| `-t` / `--topic` | uncategorized | Topic assigned to ingested papers |
| `-s` / `--source` | all | `all`, `semantic_scholar`, or `exa` |
| `--no-ingest` | off | Download PDFs only, skip OCR and ingestion |
| `--dry-run` | off | Show discovery results table, nothing downloaded |

Preview before downloading:

```bash
papermind --kb ~/Documents/KnowledgeBase fetch "SWAT calibration" -n 5 --dry-run
```

```
 Discovery Results (dry-run)
 #   Title                         Cites  PDF    Score
 1   Deep learning for SWAT+...    312    yes    18
 2   Ensemble calibration with...  88     yes    12
 3   A review of SWAT calibrat...  1240   no     8
```

## `fetch --target` — guaranteed count

Keeps fetching in multiple rounds until N papers are ingested. Automatically deduplicates against the existing KB.

```bash
papermind --kb ~/Documents/KnowledgeBase fetch "groundwater recharge estimation" --target 10 -t hydrology
```

```
Target: 10 new paper(s) for query: groundwater recharge estimation
3 already in topic 'hydrology' (will be skipped)

── Round 1: discovering up to 40 results ──
Found 7 new result(s)
  7/10 new papers ingested
── Round 2: discovering up to 80 results ──
  10/10 new papers ingested

10 new paper(s) ingested into topic 'hydrology' (13 total in topic)
```

The batch limit starts at `target * 4` and doubles each round (capped at 100). Stops after 10 rounds or when providers are exhausted.

## `ingest paper` — local PDF

Ingest a single PDF you already have on disk:

```bash
papermind --kb ~/Documents/KnowledgeBase ingest paper ~/Downloads/swat_review.pdf --topic hydrology
```

```
Ingested paper Machine Learning Calibration for SWAT+
  ID:    paper-machine-learning-calibration-2022
  Topic: hydrology
  DOI:   10.1016/j.jhydrol.2022.128422
  Path:  papers/hydrology/machine-learning-calibration-2022/paper.md
```

Papers with the same DOI are skipped automatically.

## `ingest paper <folder>` — batch ingestion

Pass a directory to ingest all PDFs inside it recursively:

```bash
papermind --kb ~/Documents/KnowledgeBase ingest paper ~/Downloads/hydro_papers/ --topic hydrology
```

```
Batch complete: 14 ingested, 2 skipped, 1 failed
  ERROR badly_scanned.pdf: OCR failed — no text extracted
```

Individual failures are logged but do not abort the batch. A single qmd reindex runs at the end.

## `crawl` — follow citation graph

Start from a paper already in the KB and follow its references to discover related work. See [citation-graph.md](citation-graph.md) for full details.

```bash
papermind --kb ~/Documents/KnowledgeBase crawl paper-swat-calibration-2022 --depth 2 --topic hydrology
```

## Notes

- OCR requires `pip install "papermind[ocr]"` and a CUDA-capable GPU.
- Only open-access papers are downloaded. Closed-access papers appear in `--dry-run` output with `no` in the PDF column.
- PDFs are staged in `~/Documents/KnowledgeBase/pdfs/` before ingestion.
- The `--no-ingest` flag is useful when you want to manually inspect PDFs before committing them to the KB.
