"""Tests for offline mode behavior."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from hydrofound.cli.main import app

runner = CliRunner()


def test_discover_blocked_offline(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])
    result = runner.invoke(app, ["--kb", str(kb), "--offline", "discover", "snow melt"])
    assert result.exit_code != 0
    assert "offline" in result.output.lower()


def test_download_blocked_offline(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])
    result = runner.invoke(app, ["--kb", str(kb), "--offline", "download", "snow melt"])
    assert result.exit_code != 0
    assert "offline" in result.output.lower()


def test_search_works_offline(tmp_path: Path) -> None:
    """Search is fully local, works in offline mode."""
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])
    # Add a searchable file
    (kb / "papers" / "test").mkdir(parents=True)
    (kb / "papers" / "test" / "paper.md").write_text(
        "---\ntype: paper\ntitle: Test\n---\n\nSnow melt content.\n"
    )
    result = runner.invoke(app, ["--kb", str(kb), "--offline", "search", "snow"])
    assert result.exit_code == 0
