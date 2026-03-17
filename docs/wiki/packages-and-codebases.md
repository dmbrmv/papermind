# Packages and Codebases

PaperMind can index Python package APIs and source trees alongside papers, making them searchable through the same interface.

## `ingest package` — installed Python package

Extracts the public API via griffe (static analysis) and writes structured docs to `kb/packages/<name>/`.

```bash
papermind --kb ~/Documents/KnowledgeBase ingest package numpy
```

```
Ingested package numpy
  ID:    package-numpy
  Files: packages/numpy/numpy.md
```

## `ingest package --from-git` — GitHub repository

Clones the repo (shallow clone), auto-detects `src/` layout, and extracts the API. The clone is cleaned up after ingestion.

```bash
papermind --kb ~/Documents/KnowledgeBase ingest package lisflood \
    --from-git https://github.com/ec-jrc/lisflood-code.git
```

Use this for packages not available on PyPI or when you want to index a specific branch/fork.

## `ingest package --source-path` — local checkout

Points griffe at a directory you already have on disk. Useful for local forks or packages under development.

```bash
papermind --kb ~/Documents/KnowledgeBase ingest package mymodel \
    --source-path /home/user/projects/mymodel/src
```

## `ingest package --docs-url` — crawl documentation site

Pairs with griffe extraction to also fetch rendered web docs. Requires Firecrawl (`pip install "papermind[browser]"` and a `PAPERMIND_FIRECRAWL_KEY`).

```bash
papermind --kb ~/Documents/KnowledgeBase ingest package xarray \
    --docs-url https://docs.xarray.dev/en/stable/api.html
```

Without `--docs-url`, only the static API (griffe) is extracted. With it, narrative docs (tutorials, guides) are also crawled and merged.

## When to use which

| Scenario | Command |
|----------|---------|
| Package installed in your environment | `ingest package <name>` |
| GitHub project not on PyPI | `ingest package <name> --from-git <url>` |
| Local development checkout | `ingest package <name> --source-path <path>` |
| Want user guide, not just API | Add `--docs-url <url>` to any of the above |

## `ingest codebase` — source tree

Walks a source directory (Python, Fortran, C, Rust), extracts function/class signatures and docstrings, and writes a summary to `kb/codebases/<name>/`.

```bash
papermind --kb ~/Documents/KnowledgeBase ingest codebase ~/src/hydrohub --name hydrohub
```

```
Walking codebase: /home/user/src/hydrohub
Rendering to: ~/Documents/KnowledgeBase/codebases/hydrohub
Ingested codebase hydrohub
  Files written: 12
  Languages detected: python
  Source files: 87
```

The `--name` flag is required. Re-running with the same name overwrites the previous entry.

## Checking what's indexed

```bash
papermind --kb ~/Documents/KnowledgeBase catalog show --topic packages
papermind --kb ~/Documents/KnowledgeBase search "interpolation" --scope packages
```

## Keeping packages current

```bash
papermind --kb ~/Documents/KnowledgeBase audit check-versions
```

Lists the latest PyPI version for each indexed package so you know when to re-ingest.

To re-ingest a package after an update, run the original `ingest package` command again — it overwrites the old entry.
