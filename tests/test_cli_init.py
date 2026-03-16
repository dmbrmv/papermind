"""Tests for papermind init command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from papermind.cli.main import app

runner = CliRunner()


def test_init_creates_folder_structure(tmp_path: Path) -> None:
    """init creates papers/, packages/, codebases/, .papermind/."""
    target = tmp_path / "MyKB"
    result = runner.invoke(app, ["init", str(target)])
    assert result.exit_code == 0
    assert (target / "papers").is_dir()
    assert (target / "packages").is_dir()
    assert (target / "codebases").is_dir()
    assert (target / ".papermind").is_dir()
    assert (target / ".papermind" / "config.toml").is_file()
    assert (target / ".gitignore").is_file()
    assert (target / "catalog.json").is_file()


def test_init_gitignore_excludes_config(tmp_path: Path) -> None:
    """Generated .gitignore excludes sensitive files."""
    target = tmp_path / "MyKB"
    runner.invoke(app, ["init", str(target)])
    gitignore = (target / ".gitignore").read_text()
    assert ".papermind/config.toml" in gitignore
    assert ".papermind/qmd/" in gitignore


def test_init_catalog_is_empty_array(tmp_path: Path) -> None:
    """catalog.json starts as empty JSON array."""
    import json

    target = tmp_path / "MyKB"
    runner.invoke(app, ["init", str(target)])
    catalog = json.loads((target / "catalog.json").read_text())
    assert catalog == []


def test_init_refuses_existing_kb(tmp_path: Path) -> None:
    """init refuses to overwrite an existing knowledge base."""
    target = tmp_path / "MyKB"
    runner.invoke(app, ["init", str(target)])
    result = runner.invoke(app, ["init", str(target)])
    assert result.exit_code != 0
    assert (
        "already exists" in result.output.lower()
        or "already initialized" in result.output.lower()
    )
