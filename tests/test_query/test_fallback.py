"""Tests for grep-based fallback search."""

from __future__ import annotations

from pathlib import Path

import pytest
from hydrofound.query.fallback import fallback_search


@pytest.fixture
def populated_kb(tmp_path: Path) -> Path:
    """KB with a few markdown files."""
    kb = tmp_path / "kb"
    (kb / "papers" / "hydrology").mkdir(parents=True)
    (kb / "codebases" / "swatplus").mkdir(parents=True)

    (kb / "papers" / "hydrology" / "snow-melt-2020.md").write_text(
        "---\ntype: paper\ntitle: Snow Melt Modeling\n---\n\n"
        "# Snow Melt Modeling\n\nTemperature-index approach for snow melt.\n"
    )
    (kb / "codebases" / "swatplus" / "subroutines.md").write_text(
        "---\ntype: codebase\nname: swatplus\n---\n\n"
        "## snow_melt.f90\n\n`subroutine calc_snow_melt(temp, melt_rate)`\n"
        "Calculate snow melt using temperature index.\n"
    )
    return kb


def test_fallback_finds_matching_content(populated_kb: Path) -> None:
    results = fallback_search(populated_kb, "snow melt")
    assert len(results) >= 1
    assert any(
        "snow" in r.title.lower() or "snow" in r.snippet.lower() for r in results
    )


def test_fallback_respects_scope(populated_kb: Path) -> None:
    results = fallback_search(populated_kb, "snow melt", scope="papers")
    assert all("papers/" in r.path for r in results)


def test_fallback_no_results(populated_kb: Path) -> None:
    results = fallback_search(populated_kb, "quantum entanglement")
    assert len(results) == 0
