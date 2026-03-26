"""Tests for papermind brief helper behavior."""

from __future__ import annotations

from papermind.cli.brief import _rerank_results
from papermind.query.fallback import SearchResult


def test_rerank_prefers_papers_over_package_indexes() -> None:
    """Paper results should outrank package index pages when scores are similar."""
    results = [
        SearchResult(
            path="packages/optuna/_index.md",
            title="Optuna Index",
            snippet="package",
            score=9.0,
        ),
        SearchResult(
            path="papers/hydrology/swat-calibration/paper.md",
            title="SWAT Calibration",
            snippet="paper",
            score=8.0,
        ),
        SearchResult(
            path="codebases/swatplus/index.md",
            title="SWAT+ Codebase",
            snippet="codebase",
            score=8.5,
        ),
    ]

    ranked = _rerank_results(results)
    assert ranked[0].path.startswith("papers/")
    assert ranked[-1].path.startswith("packages/")
