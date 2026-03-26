# Knowledge Maintenance

Commands for keeping the KB accurate, tagged, and complete.

## Freshness policy

PaperMind now distinguishes between two different states:

- `integrity`: whether a record is structurally trustworthy
- `freshness`: whether a record has been re-checked recently enough for current use

These are not the same thing. A paper can be integrity-clean and still stale.

### What counts as fresh

- `paper` entries are fresh when `last_verified` is within the last `90` days
- `package` entries are fresh when the installed or indexed version has been checked recently
- `codebase` entries should be re-ingested when their upstream source changes materially

### Verification events

Set or update `last_verified` when one of these is true:

- a paper was newly ingested and passed intake verification
- a paper was restored by the recovery workflow and passed intake verification
- a human re-checked the paper metadata, DOI, and main content manually
- a batch verification pass confirmed the record still matches external metadata

Do not mark a paper verified just because it appears in search results.

### Recommended operating cadence

| Frequency | Purpose | Command |
|-----------|---------|---------|
| After any ingestion or recovery batch | Confirm new entries are structurally valid | `papermind --kb ~/Documents/KnowledgeBase audit health --online --fail-on never` |
| Weekly | Review newly received or restored papers | `papermind --kb ~/Documents/KnowledgeBase audit intake <paper-id>` |
| Monthly | Find papers whose verification is aging out | `papermind --kb ~/Documents/KnowledgeBase audit stale` |
| Quarterly | Re-verify important topic subsets | `papermind --kb ~/Documents/KnowledgeBase audit verify <paper-id> --note "<reason>"` |
| After manual KB edits | Rebuild catalog and search index | `papermind --kb ~/Documents/KnowledgeBase reindex` |

### Recommended freshness workflow

1. Ingest or recover papers.
2. Run `audit health --online` for the whole KB.
3. Run `audit intake` for the specific new or restored paper IDs when the batch matters.
4. Mark manually reviewed papers with `audit verify`.
5. Run `audit stale` on a schedule and work down the queue by topic priority.

### Priority for re-verification

When the stale queue is large, re-verify in this order:

1. Papers used in active product or modeling work
2. Papers cited in prompts, reports, or generated summaries
3. Recently restored papers
4. Older background/reference papers

### Current policy for automation

- automatic verification is acceptable for structural checks and recovery intake
- automatic verification is not the same as scientific endorsement
- online checks should confirm DOI/title consistency, not replace paper reading
- unresolved or low-confidence records should go to quarantine, not back into the KB

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
| After bulk ingestion | `audit health --online`, `backfill`, `tags refresh`, `equations backfill` |
| Monthly | `audit stale`, `audit check-versions` |
| After adding new papers manually | `reindex` |
| After upgrading from pre-v1.3.1 | `migrate` (once) |
