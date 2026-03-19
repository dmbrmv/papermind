"""Tests for API version diffing."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from papermind.api_diff import (
    diff_apis,
    format_api_diff,
)
from papermind.cli.main import app

runner = CliRunner()


def _make_kb_with_packages(tmp_path: Path) -> Path:
    """Create KB with two package versions."""
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")

    # Old version
    old_dir = kb / "packages" / "mylib-1.0"
    old_dir.mkdir(parents=True)
    (old_dir / "api.md").write_text(
        "# mylib API\n\n"
        "### `connect(host, port, timeout)`\n\n"
        "Connect to server.\n\n"
        "### `query(sql, params)`\n\n"
        "Execute a query.\n\n"
        "### `close()`\n\n"
        "Close connection.\n\n"
    )

    # New version
    new_dir = kb / "packages" / "mylib-2.0"
    new_dir.mkdir(parents=True)
    (new_dir / "api.md").write_text(
        "# mylib API\n\n"
        "### `connect(host, port, timeout, ssl)`\n\n"
        "Connect to server (now with SSL).\n\n"
        "### `query(sql, params, fetch_size)`\n\n"
        "Execute a query (new: fetch_size).\n\n"
        "### `execute(sql)`\n\n"
        "Execute without return.\n\n"
    )

    return kb


class TestDiffAPIs:
    def test_detects_added(self, tmp_path: Path) -> None:
        kb = _make_kb_with_packages(tmp_path)
        result = diff_apis(kb, "mylib-1.0", "mylib-2.0")
        added_names = [e.function for e in result.added]
        assert "execute" in added_names

    def test_detects_removed(self, tmp_path: Path) -> None:
        kb = _make_kb_with_packages(tmp_path)
        result = diff_apis(kb, "mylib-1.0", "mylib-2.0")
        removed_names = [e.function for e in result.removed]
        assert "close" in removed_names

    def test_detects_changed_params(self, tmp_path: Path) -> None:
        kb = _make_kb_with_packages(tmp_path)
        result = diff_apis(kb, "mylib-1.0", "mylib-2.0")
        changed_names = [e.function for e in result.changed]
        assert "connect" in changed_names
        # ssl was added
        connect_change = next(e for e in result.changed if e.function == "connect")
        assert "ssl" in connect_change.detail

    def test_function_filter(self, tmp_path: Path) -> None:
        kb = _make_kb_with_packages(tmp_path)
        result = diff_apis(kb, "mylib-1.0", "mylib-2.0", function_filter="query")
        # Only query-related changes
        total = len(result.added) + len(result.removed) + len(result.changed)
        assert total >= 1
        assert all("query" in e.function for e in result.changed)

    def test_no_changes(self, tmp_path: Path) -> None:
        kb = _make_kb_with_packages(tmp_path)
        # Diff same version against itself
        result = diff_apis(kb, "mylib-1.0", "mylib-1.0")
        assert len(result.added) == 0
        assert len(result.removed) == 0
        assert len(result.changed) == 0

    def test_missing_package(self, tmp_path: Path) -> None:
        kb = _make_kb_with_packages(tmp_path)
        import pytest

        with pytest.raises(FileNotFoundError):
            diff_apis(kb, "nonexistent-1.0", "mylib-2.0")

    def test_counts(self, tmp_path: Path) -> None:
        kb = _make_kb_with_packages(tmp_path)
        result = diff_apis(kb, "mylib-1.0", "mylib-2.0")
        assert result.old_count == 3
        assert result.new_count == 3


class TestFormatAPIDiff:
    def test_format(self, tmp_path: Path) -> None:
        kb = _make_kb_with_packages(tmp_path)
        result = diff_apis(kb, "mylib-1.0", "mylib-2.0")
        text = format_api_diff(result)
        assert "API Diff" in text
        assert "Removed" in text
        assert "Added" in text
        assert "Changed" in text


class TestAPIDiffCLI:
    def test_cli(self, tmp_path: Path) -> None:
        kb = _make_kb_with_packages(tmp_path)
        result = runner.invoke(
            app,
            ["--kb", str(kb), "api-diff", "mylib-1.0", "mylib-2.0"],
        )
        assert result.exit_code == 0
        assert "API Diff" in result.output

    def test_cli_with_filter(self, tmp_path: Path) -> None:
        kb = _make_kb_with_packages(tmp_path)
        result = runner.invoke(
            app,
            ["--kb", str(kb), "api-diff", "mylib-1.0", "mylib-2.0", "-f", "connect"],
        )
        assert result.exit_code == 0

    def test_cli_missing(self, tmp_path: Path) -> None:
        kb = _make_kb_with_packages(tmp_path)
        result = runner.invoke(
            app,
            ["--kb", str(kb), "api-diff", "nonexistent", "mylib-2.0"],
        )
        assert result.exit_code == 1
