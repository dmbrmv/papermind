"""Tests for the full package ingestion pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from hydrofound.cli.main import app
from hydrofound.config import HydroFoundConfig
from hydrofound.ingestion.package import ingest_package

runner = CliRunner()


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """Initialise a throw-away knowledge base and return its path."""
    result = runner.invoke(app, ["init", str(tmp_path / "kb")])
    assert result.exit_code == 0, result.output
    return tmp_path / "kb"


@pytest.fixture()
def offline_config(kb: Path) -> HydroFoundConfig:
    """Minimal offline config — no HTTP calls allowed."""
    return HydroFoundConfig(base_path=kb, offline_only=True)


# ---------------------------------------------------------------------------
# 1. Ingest creates _index.md and api.md
# ---------------------------------------------------------------------------


def test_ingest_creates_index_and_api(
    kb: Path, offline_config: HydroFoundConfig
) -> None:
    """Ingesting a package writes packages/<name>/_index.md and api.md."""
    entry = ingest_package("hydrofound", kb, offline_config)

    pkg_dir = kb / "packages" / "hydrofound"
    assert (pkg_dir / "_index.md").exists(), "_index.md not created"
    assert (pkg_dir / "api.md").exists(), "api.md not created"
    assert entry.id == "package-hydrofound"
    assert "api.md" in entry.files


# ---------------------------------------------------------------------------
# 2. Catalog is updated correctly
# ---------------------------------------------------------------------------


def test_catalog_updated_after_ingest(
    kb: Path, offline_config: HydroFoundConfig
) -> None:
    """catalog.json and catalog.md are updated after ingestion."""
    ingest_package("hydrofound", kb, offline_config)

    catalog_data = json.loads((kb / "catalog.json").read_text())
    assert len(catalog_data) == 1
    entry = catalog_data[0]
    assert entry["type"] == "package"
    assert entry["id"] == "package-hydrofound"
    assert entry["title"] == "hydrofound"

    catalog_md = (kb / "catalog.md").read_text()
    assert "hydrofound" in catalog_md


# ---------------------------------------------------------------------------
# 3. --no-reindex flag is respected
# ---------------------------------------------------------------------------


def test_no_reindex_flag_skips_qmd(kb: Path, offline_config: HydroFoundConfig) -> None:
    """When no_reindex=True, qmd reindex is never called."""
    with patch("hydrofound.query.qmd.qmd_reindex") as mock_reindex:
        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "ingest",
                "package",
                "hydrofound",
                "--no-reindex",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_reindex.assert_not_called()


def test_no_reindex_still_writes_files(
    kb: Path, offline_config: HydroFoundConfig
) -> None:
    """--no-reindex does not prevent file writing."""
    with patch("hydrofound.query.qmd.qmd_reindex"):
        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "ingest",
                "package",
                "hydrofound",
                "--no-reindex",
            ],
        )
    assert result.exit_code == 0, result.output
    assert (kb / "packages" / "hydrofound" / "_index.md").exists()
    catalog_data = json.loads((kb / "catalog.json").read_text())
    assert len(catalog_data) == 1


# ---------------------------------------------------------------------------
# 4. Re-ingestion: files overwritten, `updated` timestamp set
# ---------------------------------------------------------------------------


def test_reingest_overwrites_and_sets_updated(
    kb: Path, offline_config: HydroFoundConfig
) -> None:
    """Ingesting the same package twice overwrites files and sets updated."""
    entry1 = ingest_package("hydrofound", kb, offline_config)
    assert entry1.updated == "", "First ingest should have no updated timestamp"

    entry2 = ingest_package("hydrofound", kb, offline_config)
    assert entry2.updated != "", "Second ingest should set updated timestamp"
    assert entry2.added == entry1.added, "added date must be preserved on re-ingest"

    # Only one entry in catalog after re-ingest
    catalog_data = json.loads((kb / "catalog.json").read_text())
    pkg_entries = [e for e in catalog_data if e["id"] == "package-hydrofound"]
    assert len(pkg_entries) == 1, "Re-ingest must not duplicate catalog entries"

    # Files are still present
    assert (kb / "packages" / "hydrofound" / "api.md").exists()
    assert (kb / "packages" / "hydrofound" / "_index.md").exists()


# ---------------------------------------------------------------------------
# 5. --docs-url stores the URL in the catalog entry
# ---------------------------------------------------------------------------


def test_docs_url_stored_in_catalog(kb: Path) -> None:
    """--docs-url is stored in catalog entry and written to _index.md."""
    config = HydroFoundConfig(base_path=kb, offline_only=False, firecrawl_key="")

    fake_docs = "# My Docs\n\nSome documentation content."

    with patch("hydrofound.ingestion.package._fetch_basic", return_value=fake_docs):
        entry = ingest_package(
            "hydrofound",
            kb,
            config,
            docs_url="https://docs.example.com/hydrofound",
        )

    assert entry.source_url == "https://docs.example.com/hydrofound"

    catalog_data = json.loads((kb / "catalog.json").read_text())
    assert catalog_data[0]["source_url"] == "https://docs.example.com/hydrofound"

    index_text = (kb / "packages" / "hydrofound" / "_index.md").read_text()
    assert "https://docs.example.com/hydrofound" in index_text

    assert "docs.md" in entry.files
    assert (kb / "packages" / "hydrofound" / "docs.md").exists()
    assert (
        "Some documentation content"
        in (kb / "packages" / "hydrofound" / "docs.md").read_text()
    )


# ---------------------------------------------------------------------------
# 6. Firecrawl is preferred when key is configured
# ---------------------------------------------------------------------------


def test_firecrawl_used_when_key_configured(kb: Path) -> None:
    """_fetch_via_firecrawl is called when firecrawl_key is set."""
    config = HydroFoundConfig(
        base_path=kb,
        offline_only=False,
        firecrawl_key="test-fc-key",
    )

    firecrawl_content = "# Firecrawl docs\n\nFetched via Firecrawl."

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"markdown": firecrawl_content}}

    with patch("httpx.post", return_value=mock_response) as mock_post:
        entry = ingest_package(
            "hydrofound",
            kb,
            config,
            docs_url="https://docs.example.com/hydrofound",
        )

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "firecrawl.dev" in call_kwargs.args[0]
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-fc-key"

    assert "docs.md" in entry.files
    docs_text = (kb / "packages" / "hydrofound" / "docs.md").read_text()
    assert "Firecrawl docs" in docs_text


# ---------------------------------------------------------------------------
# 7. PyPI URL resolution (mocked)
# ---------------------------------------------------------------------------


def test_pypi_url_resolution_used_when_no_docs_url(kb: Path) -> None:
    """When docs_url is empty, PyPI is queried for project_urls."""
    config = HydroFoundConfig(base_path=kb, offline_only=False, firecrawl_key="")

    pypi_response = MagicMock()
    pypi_response.status_code = 200
    pypi_response.json.return_value = {
        "info": {
            "project_urls": {
                "Documentation": "https://docs.example.com/hydrofound",
            }
        }
    }

    basic_docs = "# Docs fetched via basic HTTP"

    with (
        patch("httpx.get", return_value=pypi_response),
        patch("hydrofound.ingestion.package._fetch_basic", return_value=basic_docs),
    ):
        entry = ingest_package("hydrofound", kb, config, docs_url="")

    assert entry.source_url == "https://docs.example.com/hydrofound"
    assert "docs.md" in entry.files


# ---------------------------------------------------------------------------
# 8. CLI package command — happy path
# ---------------------------------------------------------------------------


def test_cli_ingest_package_command(kb: Path) -> None:
    """CLI `ingest package` command succeeds and creates expected files."""
    result = runner.invoke(
        app,
        [
            "--kb",
            str(kb),
            "ingest",
            "package",
            "hydrofound",
            "--no-reindex",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Ingested" in result.output
    assert (kb / "packages" / "hydrofound" / "_index.md").exists()
    assert (kb / "packages" / "hydrofound" / "api.md").exists()


# ---------------------------------------------------------------------------
# 9. offline_only skips all HTTP (no docs fetched even if URL provided)
# ---------------------------------------------------------------------------


def test_offline_mode_skips_http(kb: Path) -> None:
    """With offline_only=True, no HTTP calls are made even if docs_url is set."""
    config = HydroFoundConfig(base_path=kb, offline_only=True)

    with patch("httpx.get") as mock_get, patch("httpx.post") as mock_post:
        entry = ingest_package(
            "hydrofound",
            kb,
            config,
            docs_url="https://docs.example.com/hydrofound",
        )

    mock_get.assert_not_called()
    mock_post.assert_not_called()
    assert "docs.md" not in entry.files
