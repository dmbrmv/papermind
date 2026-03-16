"""Tests for the qmd subprocess wrapper (qmd v2 API)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from papermind.query.fallback import SearchResult
from papermind.query.qmd import is_qmd_available, qmd_reindex, qmd_search

# ---------------------------------------------------------------------------
# is_qmd_available
# ---------------------------------------------------------------------------


def test_is_qmd_available_returns_true_when_found() -> None:
    with patch("papermind.query.qmd.shutil.which", return_value="/usr/bin/qmd"):
        assert is_qmd_available() is True


def test_is_qmd_available_returns_false_when_not_found() -> None:
    with patch("papermind.query.qmd.shutil.which", return_value=None):
        assert is_qmd_available() is False


# ---------------------------------------------------------------------------
# qmd_search — command construction (qmd v2: no --dir flag)
# ---------------------------------------------------------------------------


def _make_completed_process(
    stdout: str = "[]",
    returncode: int = 0,
    stderr: str = "",
) -> MagicMock:
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.stdout = stdout
    proc.stderr = stderr
    proc.returncode = returncode
    return proc


def test_qmd_search_command_construction(tmp_path: Path) -> None:
    """qmd v2 search uses: qmd search <query> --json."""
    kb = tmp_path / "kb"
    kb.mkdir()

    with patch(
        "papermind.query.qmd.subprocess.run",
        return_value=_make_completed_process(stdout="[]"),
    ) as mock_run:
        qmd_search(kb, "soil moisture", limit=5)

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd == ["qmd", "search", "soil moisture", "--json"]


# ---------------------------------------------------------------------------
# qmd_search — JSON output parsing (qmd v2 format)
# ---------------------------------------------------------------------------


def test_qmd_search_parses_json_output(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()

    # qmd v2 uses "file" field with qmd:// URIs
    payload = [
        {
            "file": "qmd://my-kb/papers/hydro/runoff.md",
            "title": "Runoff Estimation",
            "snippet": "curve number approach",
            "score": 0.87,
        },
        {
            "file": "qmd://my-kb/packages/swatplus/api.md",
            "title": "SWAT+ API",
            "snippet": "parameter table",
            "score": 0.62,
        },
    ]

    with patch(
        "papermind.query.qmd.subprocess.run",
        return_value=_make_completed_process(stdout=json.dumps(payload)),
    ):
        results = qmd_search(kb, "runoff")

    assert len(results) == 2
    assert isinstance(results[0], SearchResult)
    assert results[0].path == "papers/hydro/runoff.md"
    assert results[0].title == "Runoff Estimation"
    assert results[0].score == pytest.approx(0.87)
    assert results[1].path == "packages/swatplus/api.md"


def test_qmd_search_strips_line_numbers_from_path(tmp_path: Path) -> None:
    """qmd v2 appends :linenum to file paths — strip them."""
    kb = tmp_path / "kb"
    kb.mkdir()

    payload = [
        {
            "file": "qmd://kb/papers/swat.md:42",
            "title": "SWAT",
            "snippet": "text",
            "score": 0.5,
        },
    ]

    with patch(
        "papermind.query.qmd.subprocess.run",
        return_value=_make_completed_process(stdout=json.dumps(payload)),
    ):
        results = qmd_search(kb, "swat")

    assert results[0].path == "papers/swat.md"


def test_qmd_search_scope_filters_results(tmp_path: Path) -> None:
    """Scope filters results to matching paths."""
    kb = tmp_path / "kb"
    kb.mkdir()

    payload = [
        {"file": "qmd://kb/papers/a.md", "title": "A", "snippet": "", "score": 0.9},
        {"file": "qmd://kb/packages/b.md", "title": "B", "snippet": "", "score": 0.8},
    ]

    with patch(
        "papermind.query.qmd.subprocess.run",
        return_value=_make_completed_process(stdout=json.dumps(payload)),
    ):
        results = qmd_search(kb, "test", scope="papers")

    assert len(results) == 1
    assert results[0].path == "papers/a.md"


def test_qmd_search_returns_empty_list_for_empty_json(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()

    with patch(
        "papermind.query.qmd.subprocess.run",
        return_value=_make_completed_process(stdout="[]"),
    ):
        results = qmd_search(kb, "anything")

    assert results == []


# ---------------------------------------------------------------------------
# qmd_search — error handling
# ---------------------------------------------------------------------------


def test_qmd_search_raises_on_nonzero_exit(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()

    with patch(
        "papermind.query.qmd.subprocess.run",
        return_value=_make_completed_process(
            stdout="", returncode=1, stderr="index not found"
        ),
    ):
        with pytest.raises(RuntimeError, match="qmd search failed"):
            qmd_search(kb, "flood")


# ---------------------------------------------------------------------------
# qmd_reindex — qmd v2 uses collection refresh
# ---------------------------------------------------------------------------


def test_qmd_reindex_calls_collection_refresh(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()

    with (
        patch("papermind.query.qmd.shutil.which", return_value="/usr/bin/qmd"),
        patch(
            "papermind.query.qmd.subprocess.run",
            return_value=_make_completed_process(),
        ) as mock_run,
    ):
        qmd_reindex(kb)

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd == ["qmd", "collection", "refresh"]


def test_qmd_reindex_skips_when_qmd_not_available(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()

    with (
        patch("papermind.query.qmd.shutil.which", return_value=None),
        patch("papermind.query.qmd.subprocess.run") as mock_run,
    ):
        qmd_reindex(kb)

    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# E1: qmd_search passes cwd=str(kb_path) to subprocess.run (Batch A fix)
# ---------------------------------------------------------------------------


def test_qmd_search_passes_cwd(tmp_path: Path) -> None:
    """subprocess.run is called with cwd=str(kb_path) so qmd finds the KB."""
    kb = tmp_path / "kb"
    kb.mkdir()

    with patch(
        "papermind.query.qmd.subprocess.run",
        return_value=_make_completed_process(stdout="[]"),
    ) as mock_run:
        qmd_search(kb, "runoff")

    mock_run.assert_called_once()
    kwargs = mock_run.call_args[1]
    assert kwargs.get("cwd") == str(kb), (
        f"Expected cwd={str(kb)!r}, got cwd={kwargs.get('cwd')!r}"
    )
