# Searching

## Basic search

```bash
papermind --kb ~/Documents/KnowledgeBase search "evapotranspiration calibration"
```

Results are shown in a table with title, path, score, and a snippet.

## Options

| Flag | Description |
|------|-------------|
| `--topic` / `-t` | Filter to a topic (e.g. `hydrology`) |
| `--year` / `-y` | Only papers from this year onward |
| `--scope` | Restrict to `papers`, `packages`, or `codebases` |
| `--limit` | Max results (default 10, max 200) |

```bash
# Papers from 2020 onward in the hydrology topic
papermind --kb ~/Documents/KnowledgeBase search "groundwater recharge" --topic hydrology --year 2020

# Only search package docs
papermind --kb ~/Documents/KnowledgeBase search "optimize" --scope packages

# Wider result set
papermind --kb ~/Documents/KnowledgeBase search "streamflow" --limit 25
```

## How `--topic` maps to scope

`--topic hydrology` is shorthand for `--scope papers/hydrology`. Both are equivalent:

```bash
papermind --kb ~/Documents/KnowledgeBase search "baseflow" --topic hydrology
papermind --kb ~/Documents/KnowledgeBase search "baseflow" --scope papers/hydrology
```

## qmd vs fallback search

**With qmd installed** (semantic search):
- BM25 + vector embedding + LLM reranking
- Query is interpreted semantically — "infiltration" also matches papers about Green-Ampt
- If qmd returns no results, search automatically falls back to grep

**Without qmd** (grep fallback):
- Case-insensitive substring match across all `.md` files in the KB
- All `--year`, `--topic`, and `--scope` filters still apply
- Suitable for keyword lookups and offline use

## Alias expansion

Queries are expanded using `aliases.yaml` before search. This means a search for `groundwater` also matches papers tagged with `baseflow`, `aquifer`, `recharge`, `gw`, `gwflow`, `water_table`, `percolation`.

Current alias groups include:

| Query term | Also searches for |
|-----------|-------------------|
| `groundwater` | baseflow, aquifer, recharge, gwflow |
| `calibration` | parameter_estimation, cma-es, nsga-ii, sufi-2 |
| `machine_learning` | lstm, neural_network, surrogate, deep_learning |
| `evapotranspiration` | penman, hargreaves, pet, aet |
| `flood` | inundation, floodplain, return_period |
| `uncertainty` | ensemble, bayesian, monte_carlo |

Alias groups are defined in `src/papermind/aliases.yaml`. Add your own domain terms there.

## `context-pack` — compressed briefing for agents

Generates a dense, budget-controlled briefing on a topic, sorted by citation richness. Designed to be pasted into `CLAUDE.md` or a session preamble.

```bash
papermind --kb ~/Documents/KnowledgeBase context-pack hydrology --max-tokens 2000
```

Write to file:

```bash
papermind --kb ~/Documents/KnowledgeBase context-pack diff_hydro -n 3000 -o briefing.md
```

Output format:

```markdown
# PaperMind Briefing: hydrology
> 12 papers in KB

## 1. Deep learning surrogate for SWAT+ calibration
2022 | DOI: 10.1016/j.jhydrol.2022.128422 | 14 refs, 8 citations
Tags: calibration, machine_learning, swat, lstm

This study presents a deep learning surrogate...

Path: papers/hydrology/deep-learning-swat-2022/paper.md

## 2. ...
```

The `context-pack` argument is the topic name (required). Use `catalog show` to see available topics.
