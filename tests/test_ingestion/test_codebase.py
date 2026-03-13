"""Tests for codebase tree walker."""

from __future__ import annotations

from pathlib import Path

import pytest
from hydrofound.ingestion.codebase import walk_codebase


@pytest.fixture
def sample_codebase(tmp_path: Path) -> Path:
    """Create a minimal multi-language codebase."""
    src = tmp_path / "myproject"
    src.mkdir()

    # Fortran file
    (src / "snow_melt.f90").write_text(
        "! Snow melt calculation module\n"
        "module snow_melt_mod\n"
        "  implicit none\n"
        "contains\n"
        "  subroutine calc_snow_melt(temp, melt_rate, result)\n"
        "    ! Calculate snow melt using temperature index method\n"
        "    real, intent(in) :: temp, melt_rate\n"
        "    real, intent(out) :: result\n"
        "    result = max(0.0, (temp - 0.0) * melt_rate)\n"
        "  end subroutine\n"
        "end module\n"
    )

    # Python file
    (src / "utils.py").write_text(
        '"""Utility functions."""\n\n\n'
        "def compute_area(radius: float) -> float:\n"
        '    """Compute circle area."""\n'
        "    import math\n"
        "    return math.pi * radius ** 2\n"
    )

    # README
    (src / "README.md").write_text("# My Project\n\nA test project.\n")

    # Gitignore (should be respected)
    (src / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    pycache = src / "__pycache__"
    pycache.mkdir()
    (pycache / "utils.cpython-311.pyc").write_bytes(b"bytecode")

    return src


def test_walk_detects_languages(sample_codebase: Path) -> None:
    result = walk_codebase(sample_codebase)
    assert "fortran" in result.languages
    assert "python" in result.languages


def test_walk_extracts_fortran_signatures(sample_codebase: Path) -> None:
    result = walk_codebase(sample_codebase)
    sigs = result.signatures["snow_melt.f90"]
    assert any("calc_snow_melt" in s.name for s in sigs)


def test_walk_extracts_python_signatures(sample_codebase: Path) -> None:
    result = walk_codebase(sample_codebase)
    sigs = result.signatures["utils.py"]
    assert any("compute_area" in s.name for s in sigs)


def test_walk_respects_gitignore(sample_codebase: Path) -> None:
    result = walk_codebase(sample_codebase)
    all_files = list(result.signatures.keys())
    assert not any("__pycache__" in f for f in all_files)
    assert not any(".pyc" in f for f in all_files)


def test_walk_includes_readme(sample_codebase: Path) -> None:
    result = walk_codebase(sample_codebase)
    assert result.readme_content is not None
    assert "My Project" in result.readme_content
