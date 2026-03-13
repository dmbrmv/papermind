"""Tests for codebase → markdown renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from hydrofound.ingestion.codebase import CodebaseMap, SignatureInfo
from hydrofound.ingestion.codebase_render import render_codebase


@pytest.fixture
def sample_map() -> CodebaseMap:
    return CodebaseMap(
        name="myproject",
        root=Path("/fake"),
        languages={"python", "fortran"},
        file_tree=["utils.py", "snow_melt.f90", "README.md"],
        signatures={
            "utils.py": [
                SignatureInfo(
                    name="compute_area",
                    kind="function",
                    line=4,
                    docstring="Compute circle area.",
                )
            ],
            "snow_melt.f90": [
                SignatureInfo(
                    name="calc_snow_melt",
                    kind="subroutine",
                    line=5,
                    docstring="Calculate snow melt.",
                )
            ],
        },
        readme_content="# My Project\n\nA test project.\n",
    )


def test_render_produces_index(sample_map: CodebaseMap, tmp_path: Path) -> None:
    files = render_codebase(sample_map, tmp_path)
    index = tmp_path / "_index.md"
    assert index.exists()
    content = index.read_text()
    assert "myproject" in content.lower()
    assert "python" in content.lower()


def test_render_produces_structure(sample_map: CodebaseMap, tmp_path: Path) -> None:
    render_codebase(sample_map, tmp_path)
    structure = tmp_path / "structure.md"
    assert structure.exists()
    content = structure.read_text()
    assert "utils.py" in content
    assert "snow_melt.f90" in content


def test_render_produces_signatures(sample_map: CodebaseMap, tmp_path: Path) -> None:
    render_codebase(sample_map, tmp_path)
    sigs = tmp_path / "signatures.md"
    assert sigs.exists()
    content = sigs.read_text()
    assert "compute_area" in content
    assert "calc_snow_melt" in content


def test_render_returns_created_paths(sample_map: CodebaseMap, tmp_path: Path) -> None:
    """render_codebase returns exactly the paths it created."""
    created = render_codebase(sample_map, tmp_path)
    assert len(created) == 3
    for p in created:
        assert p.exists()


def test_render_index_has_frontmatter(sample_map: CodebaseMap, tmp_path: Path) -> None:
    """_index.md contains YAML frontmatter with type: codebase."""
    render_codebase(sample_map, tmp_path)
    content = (tmp_path / "_index.md").read_text()
    assert "type: codebase" in content
    assert "name: myproject" in content


def test_render_readme_included_in_index(
    sample_map: CodebaseMap, tmp_path: Path
) -> None:
    """README content is embedded in _index.md when present."""
    render_codebase(sample_map, tmp_path)
    content = (tmp_path / "_index.md").read_text()
    assert "A test project." in content


def test_render_no_readme(tmp_path: Path) -> None:
    """render_codebase handles missing readme_content gracefully."""
    cb = CodebaseMap(
        name="noreadme",
        root=Path("/fake"),
        languages={"python"},
        file_tree=["main.py"],
        signatures={},
        readme_content=None,
    )
    render_codebase(cb, tmp_path)
    content = (tmp_path / "_index.md").read_text()
    assert "## README" not in content


def test_render_creates_output_dir(sample_map: CodebaseMap, tmp_path: Path) -> None:
    """output_dir is created if it does not exist."""
    nested = tmp_path / "a" / "b" / "c"
    assert not nested.exists()
    render_codebase(sample_map, nested)
    assert nested.is_dir()
    assert (nested / "_index.md").exists()
