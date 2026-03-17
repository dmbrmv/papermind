# Citation Graph

PaperMind tracks `cites` and `cited_by` DOI lists in each paper's frontmatter. These are populated during discovery (via Semantic Scholar) or retroactively via `backfill`.

## `backfill` — populate citation data for existing papers

Queries OpenAlex for every paper in the KB that has a DOI but no citation data yet. Writes `cites` and `cited_by` lists to frontmatter.

```bash
papermind --kb ~/Documents/KnowledgeBase backfill
```

```
12 paper(s) to backfill
  OK   10.1016/j.jhydrol.2022.128422 — 34 refs, 8 citations
  OK   10.5194/hess-26-1523-2022     — 12 refs, 21 citations
  SKIP 10.1029/2019WR026252          — no data from SS
  ...
11 enriched, 1 skipped (no data)
```

Papers without DOIs, or papers already having citation data, are skipped. Run `backfill` after any bulk ingestion.

## `crawl` — follow references to expand the KB

Reads citation DOIs from a seed paper's frontmatter, checks open-access availability via OpenAlex, and downloads + ingests the ones it can reach.

```bash
papermind --kb ~/Documents/KnowledgeBase crawl paper-swat-calibration-2022 \
    --depth 2 --topic hydrology
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--depth` / `-d` | 1 | How many citation levels to follow |
| `--target` / `-n` | 10 | Max new papers to ingest |
| `--topic` / `-t` | uncategorized | Topic for ingested papers |
| `--direction` | cites | `cites` (references), `cited_by`, or `both` |

Follow papers that cite your seed (inward links):

```bash
papermind --kb ~/Documents/KnowledgeBase crawl paper-lstm-streamflow \
    --direction cited_by --depth 1 --target 20
```

Follow both directions:

```bash
papermind --kb ~/Documents/KnowledgeBase crawl paper-lstm-streamflow \
    --direction both --depth 1 --target 15
```

The OpenAlex filter runs before any downloads — only open-access DOIs proceed to download. Closed-access DOIs are silently skipped (too noisy to log when processing 100+ DOIs).

Run `backfill` before `crawl` if the seed paper was ingested without citation data.

## `related` — show citation connections within the KB

Shows which papers already in the KB are linked to a given paper by citation. Only papers already ingested are shown — this is not a discovery tool.

```bash
papermind --kb ~/Documents/KnowledgeBase related paper-swat-calibration-2022
```

```
Related papers for: Deep learning surrogate for SWAT+ calibration
DOI: 10.1016/j.jhydrol.2022.128422

References (this paper cites)
 ID                              Title                        DOI
 paper-lstm-streamflow-2019      LSTM for streamflow pred...  10.1029/...
 paper-cma-es-calibration-2018   CMA-ES parameter estimat...  10.5194/...

Cited by (papers that cite this one)
 paper-swat-review-2023          A review of SWAT+ calibra...  10.1016/...

3 related paper(s) in KB
```

`related` checks both directions: papers that this paper cites, and papers in the KB that cite this paper. It also scans other papers' frontmatter for reverse links, so connections are found even when only one paper has citation data.

## How citation data flows through the system

1. **During `fetch`**: Semantic Scholar returns `cites` / `cited_by` DOI lists alongside metadata. These are written to frontmatter during ingestion.
2. **During `crawl`**: OpenAlex is queried per-DOI as papers are ingested, so newly crawled papers also get citation data.
3. **Via `backfill`**: For papers that were ingested without citation data (e.g., from local PDFs), `backfill` queries OpenAlex retrospectively.
4. **In `related`**: Reads frontmatter only — no network calls. Shows the subset of the citation graph that exists inside the KB.
