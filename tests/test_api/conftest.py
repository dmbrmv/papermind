"""Shared fixtures for API tests."""

from __future__ import annotations

from pathlib import Path

import frontmatter as fm_lib
import pytest

fastapi = pytest.importorskip(
    "fastapi", reason="fastapi not installed (pip install 'papermind[api]')"
)

from fastapi.testclient import TestClient  # noqa: E402

from papermind.api.app import create_app  # noqa: E402
from papermind.catalog.index import CatalogEntry, CatalogIndex  # noqa: E402


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    """Create a minimal KB with test data."""
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")

    # Add a paper
    paper_dir = kb / "papers" / "hydrology" / "test-paper"
    paper_dir.mkdir(parents=True)
    post = fm_lib.Post("# Test Paper\n\nContent about hydrology.\n")
    post.metadata = {
        "type": "paper",
        "id": "paper-test-2020",
        "title": "Test Paper on Hydrology",
        "topic": "hydrology",
        "doi": "10.1234/test2020",
        "year": 2020,
        "abstract": "A paper about water.",
        "tags": ["hydrology", "calibration"],
    }
    (paper_dir / "paper.md").write_text(fm_lib.dumps(post))

    # Add a second paper
    paper_dir2 = kb / "papers" / "hydrology" / "swat-paper"
    paper_dir2.mkdir(parents=True)
    post2 = fm_lib.Post("# SWAT+ Model\n\nSWAT+ calibration details.\n")
    post2.metadata = {
        "type": "paper",
        "id": "paper-swat-2021",
        "title": "SWAT+ Model Calibration",
        "topic": "hydrology",
        "doi": "10.5678/swat2021",
        "year": 2021,
        "tags": ["swat", "calibration"],
    }
    (paper_dir2 / "paper.md").write_text(fm_lib.dumps(post2))

    # Update catalog
    catalog = CatalogIndex(kb)
    catalog.add(
        CatalogEntry(
            id="paper-test-2020",
            type="paper",
            path="papers/hydrology/test-paper/paper.md",
            title="Test Paper on Hydrology",
            topic="hydrology",
            doi="10.1234/test2020",
            tags=["hydrology", "calibration"],
        )
    )
    catalog.add(
        CatalogEntry(
            id="paper-swat-2021",
            type="paper",
            path="papers/hydrology/swat-paper/paper.md",
            title="SWAT+ Model Calibration",
            topic="hydrology",
            doi="10.5678/swat2021",
            tags=["swat", "calibration"],
        )
    )

    return kb


@pytest.fixture
def client(kb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a test client bound to the test KB.

    Sets PAPERMIND_ALLOWED_PATHS to include tmp_path so analysis endpoints
    can access test files created in tmp_path.
    """
    monkeypatch.setenv("PAPERMIND_ALLOWED_PATHS", f"{kb}:{tmp_path}")
    app = create_app(kb)
    return TestClient(app)
