"""Tests for the qmd subprocess wrapper."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hydrofound.query.fallback import SearchResult
from hydrofound.query.qmd import is_qmd_available, qmd_reindex, qmd_search

# ---------------------------------------------------------------------------
# is_qmd_available
# ---------------------------------------------------------------------------


def test_is_qmd_available_returns_true_when_found() -> None:
    with patch("hydrofound.query.qmd.shutil.which", return_value="/usr/bin/qmd"):
        assert is_qmd_available() is True


def test_is_qmd_available_returns_false_when_not_found() -> None:
    with patch("hydrofound.query.qmd.shutil.which", return_value=None):
        assert is_qmd_available() is False


# ---------------------------------------------------------------------------
# qmd_search — command construction
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
    """qmd search must be invoked with the expected argument list."""
    kb = tmp_path / "kb"
    kb.mkdir()

    with patch(
        "hydrofound.query.qmd.subprocess.run",
        return_value=_make_completed_process(stdout="[]"),
    ) as mock_run:
        qmd_search(kb, "soil moisture", limit=5)

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "qmd"
    assert cmd[1] == "search"
    assert "soil moisture" in cmd
    assert "--dir" in cmd
    assert str(kb) in cmd
    assert "--limit" in cmd
    assert "5" in cmd
    assert "--json" in cmd


def test_qmd_search_command_without_scope_uses_kb_root(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()

    with patch(
        "hydrofound.query.qmd.subprocess.run",
        return_value=_make_completed_process(stdout="[]"),
    ) as mock_run:
        qmd_search(kb, "rainfall", scope="", limit=10)

    cmd = mock_run.call_args[0][0]
    dir_idx = cmd.index("--dir")
    assert cmd[dir_idx + 1] == str(kb)


# ---------------------------------------------------------------------------
# qmd_search — scope → directory filter
# ---------------------------------------------------------------------------


def test_qmd_search_scope_translates_to_subdirectory(tmp_path: Path) -> None:
    """When scope is provided the search dir should be kb_path / scope."""
    kb = tmp_path / "kb"
    kb.mkdir()

    with patch(
        "hydrofound.query.qmd.subprocess.run",
        return_value=_make_completed_process(stdout="[]"),
    ) as mock_run:
        qmd_search(kb, "evapotranspiration", scope="papers", limit=10)

    cmd = mock_run.call_args[0][0]
    dir_idx = cmd.index("--dir")
    assert cmd[dir_idx + 1] == str(kb / "papers")


# ---------------------------------------------------------------------------
# qmd_search — JSON output parsing
# ---------------------------------------------------------------------------


def test_qmd_search_parses_json_output(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()

    payload = [
        {
            "path": "papers/hydro/runoff.md",
            "title": "Runoff Estimation",
            "snippet": "…curve number approach…",
            "score": 0.87,
        },
        {
            "path": "packages/swatplus/api.md",
            "title": "SWAT+ API",
            "snippet": "…parameter table…",
            "score": 0.62,
        },
    ]

    with patch(
        "hydrofound.query.qmd.subprocess.run",
        return_value=_make_completed_process(stdout=json.dumps(payload)),
    ):
        results = qmd_search(kb, "runoff")

    assert len(results) == 2
    assert isinstance(results[0], SearchResult)
    assert results[0].path == "papers/hydro/runoff.md"
    assert results[0].title == "Runoff Estimation"
    assert results[0].snippet == "…curve number approach…"
    assert results[0].score == pytest.approx(0.87)
    assert results[1].score == pytest.approx(0.62)


def test_qmd_search_title_falls_back_to_stem_when_missing(tmp_path: Path) -> None:
    """If 'title' is absent in a result item, use Path.stem of 'path'."""
    kb = tmp_path / "kb"
    kb.mkdir()

    payload = [{"path": "papers/snow-melt-2020.md", "snippet": "…text…", "score": 0.5}]

    with patch(
        "hydrofound.query.qmd.subprocess.run",
        return_value=_make_completed_process(stdout=json.dumps(payload)),
    ):
        results = qmd_search(kb, "snow")

    assert results[0].title == "snow-melt-2020"


def test_qmd_search_returns_empty_list_for_empty_json(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()

    with patch(
        "hydrofound.query.qmd.subprocess.run",
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
        "hydrofound.query.qmd.subprocess.run",
        return_value=_make_completed_process(
            stdout="", returncode=1, stderr="index not found"
        ),
    ):
        with pytest.raises(RuntimeError, match="qmd search failed"):
            qmd_search(kb, "flood")


# ---------------------------------------------------------------------------
# qmd_reindex — command construction
# ---------------------------------------------------------------------------


def test_qmd_reindex_command_construction(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()

    with (
        patch("hydrofound.query.qmd.shutil.which", return_value="/usr/bin/qmd"),
        patch(
            "hydrofound.query.qmd.subprocess.run",
            return_value=_make_completed_process(),
        ) as mock_run,
    ):
        qmd_reindex(kb)

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd == ["qmd", "index", str(kb)]


def test_qmd_reindex_skips_when_qmd_not_available(tmp_path: Path) -> None:
    """When qmd is absent, reindex must return silently without calling subprocess."""
    kb = tmp_path / "kb"
    kb.mkdir()

    with (
        patch("hydrofound.query.qmd.shutil.which", return_value=None),
        patch("hydrofound.query.qmd.subprocess.run") as mock_run,
    ):
        qmd_reindex(kb)

    mock_run.assert_not_called()
