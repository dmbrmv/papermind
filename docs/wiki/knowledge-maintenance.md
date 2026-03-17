# Knowledge Maintenance

Commands for keeping the KB accurate, tagged, and complete.

## `tags refresh` — recompute TF-IDF tags

Analyzes the full paper corpus and assigns distinctive keywords to each paper. Tags are written to the `tags` field in frontmatter and appear in `context-pack` output.

```bash
papermind --kb ~/Documents/KnowledgeBase tags refresh
```

```
  paper-swat-calibration-2022         → calibration, cma-es, swat, sensitivity, lstm
  paper-groundwater-recharge-2021     → aquifer, recharge, modflow, darcy, percolation
  ...
47 paper(s) tagged
```

Preview without writing:

```bash
papermind --kb ~/Documents/KnowledgeBase tags refresh --dry-run
```

Adjust the number of tags per paper:

```bash
papermind --kb ~/Documents/KnowledgeBase tags refresh --max-tags 5
```

Run `tags refresh` after any significant batch ingestion so new papers are properly described.

## `equations backfill` — extract equations from papers

Extracts LaTeX equation blocks (`$$...$$`) from all paper markdown files and stores them in frontmatter. Run once after ingestion to make equations queryable.

```bash
papermind --kb ~/Documents/KnowledgeBase equations backfill
```

```
  paper-nse-objective-2019           → 3 equation(s)
  paper-swat-et-equations-2021       → 12 equation(s)
  paper-lstm-streamflow-2022         → 0 equation(s)
...
8 paper(s) updated
```

View extracted equations for a specific paper:

```bash
papermind --kb ~/Documents/KnowledgeBase equations show paper-swat-et-equations-2021
```

## `tables backfill` — extract tables from papers

Extracts markdown tables from paper files and stores them in frontmatter.

```bash
papermind --kb ~/Documents/KnowledgeBase tables backfill
```

View tables for a specific paper:

```bash
papermind --kb ~/Documents/KnowledgeBase tables show paper-swat-calibration-2022
```

## `audit stale` — find papers not reviewed recently

Lists papers whose `last_verified` date is older than a threshold (default: 90 days). Papers without `last_verified` are always flagged.

```bash
papermind --kb ~/Documents/KnowledgeBase audit stale
```

```
 Stale papers (>90 days)
 ID                              Title                    Status
 paper-lstm-streamflow-2019      LSTM for streamflow...   never verified
 paper-cn-review-2020            Curve Number review...   verified 2025-08-01
```

Adjust the window:

```bash
papermind --kb ~/Documents/KnowledgeBase audit stale --days 180
```

## `audit verify` — mark a paper as reviewed

```bash
papermind --kb ~/Documents/KnowledgeBase audit verify paper-lstm-streamflow-2019
papermind --kb ~/Documents/KnowledgeBase audit verify paper-cn-review-2020 \
    --note "confirmed methods match current SWAT+ implementation"
```

Sets `last_verified` to today's date in frontmatter.

## `audit check-versions` — check package freshness

Checks PyPI for the latest version of each indexed package:

```bash
papermind --kb ~/Documents/KnowledgeBase audit check-versions
```

```
  numpy                          latest: 2.2.3
  xarray                         latest: 2024.11.0
  pySWATPlus                     not on PyPI
```

Re-ingest any packages with new versions by running `ingest package <name>` again.

## `pitfall-add` — attach anti-pattern warnings

Links a code pattern to a warning message on a paper. When `watch` scans a source file matching the pattern, the warning is surfaced.

```bash
papermind --kb ~/Documents/KnowledgeBase pitfall-add paper-swat-cn-2019 \
    --pattern "CN.*retention" \
    --warning "SWAT+ CN has two mutually exclusive code paths (daily vs sub-daily)"
```

List all pitfalls across the KB:

```bash
papermind --kb ~/Documents/KnowledgeBase pitfall-list
```

## `migrate` — convert legacy flat layout

If your KB was created before v1.3.1, papers are stored as `papers/topic/slug.md`. The current layout uses `papers/topic/slug/paper.md`. Run once to convert:

```bash
papermind --kb ~/Documents/KnowledgeBase migrate
```

The command is idempotent — already-migrated papers are skipped. Catalog and qmd index are rebuilt automatically.

## `reindex` — rebuild catalog from filesystem

Use when `catalog.json` is out of sync with the actual files (e.g., after manual edits or a failed ingestion):

```bash
papermind --kb ~/Documents/KnowledgeBase reindex
```

Scans all `.md` frontmatter, rebuilds `catalog.json` and `catalog.md`, and triggers a qmd reindex.

## Suggested maintenance schedule

| Frequency | Command |
|-----------|---------|
| After bulk ingestion | `backfill`, `tags refresh`, `equations backfill` |
| Monthly | `audit stale`, `audit check-versions` |
| After adding new papers manually | `reindex` |
| After upgrading from pre-v1.3.1 | `migrate` (once) |
