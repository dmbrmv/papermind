"""Tests for ingest CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from hydrofound.cli.main import app

runner = CliRunner()


def test_ingest_codebase_creates_files(tmp_path: Path) -> None:
    # Setup: init a KB, create a sample codebase
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])
    code = tmp_path / "code"
    code.mkdir()
    (code / "main.py").write_text("def hello(): pass\n")

    result = runner.invoke(
        app, ["--kb", str(kb), "ingest", "codebase", str(code), "--name", "mycode"]
    )
    assert result.exit_code == 0
    assert (kb / "codebases" / "mycode" / "_index.md").exists()
    assert (kb / "codebases" / "mycode" / "structure.md").exists()


def test_ingest_codebase_no_reindex_flag(tmp_path: Path) -> None:
    """--no-reindex skips qmd reindex."""
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])
    code = tmp_path / "code"
    code.mkdir()
    (code / "main.py").write_text("def hello(): pass\n")

    result = runner.invoke(
        app,
        [
            "--kb",
            str(kb),
            "ingest",
            "codebase",
            str(code),
            "--name",
            "mycode",
            "--no-reindex",
        ],
    )
    assert result.exit_code == 0
    # catalog.json should still be updated
    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 1


def test_ingest_codebase_catalog_entry_type(tmp_path: Path) -> None:
    """Catalog entry has type=codebase and correct id."""
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])
    code = tmp_path / "code"
    code.mkdir()
    (code / "utils.py").write_text("def add(a, b): return a + b\n")

    runner.invoke(
        app,
        ["--kb", str(kb), "ingest", "codebase", str(code), "--name", "myutils"],
    )
    catalog = json.loads((kb / "catalog.json").read_text())
    assert len(catalog) == 1
    entry = catalog[0]
    assert entry["type"] == "codebase"
    assert entry["id"] == "codebase-myutils"
    assert entry["title"] == "myutils"


def test_ingest_codebase_updates_catalog_md(tmp_path: Path) -> None:
    """catalog.md is regenerated and includes the new codebase."""
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])
    code = tmp_path / "code"
    code.mkdir()
    (code / "snow.f90").write_text("subroutine calc(x)\n  real x\nend subroutine\n")

    runner.invoke(
        app,
        ["--kb", str(kb), "ingest", "codebase", str(code), "--name", "snowmodel"],
    )
    catalog_md = (kb / "catalog.md").read_text()
    assert "snowmodel" in catalog_md


def test_ingest_codebase_signatures_file(tmp_path: Path) -> None:
    """signatures.md is created and contains function names."""
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])
    code = tmp_path / "code"
    code.mkdir()
    (code / "math.py").write_text("def square(x):\n    return x * x\n")

    runner.invoke(
        app,
        ["--kb", str(kb), "ingest", "codebase", str(code), "--name", "mathlib"],
    )
    sigs = (kb / "codebases" / "mathlib" / "signatures.md").read_text()
    assert "square" in sigs


def test_ingest_codebase_no_kb_exits_nonzero(tmp_path: Path) -> None:
    """Without --kb the command exits with non-zero code."""
    code = tmp_path / "code"
    code.mkdir()
    (code / "main.py").write_text("pass\n")

    result = runner.invoke(app, ["ingest", "codebase", str(code), "--name", "x"])
    assert result.exit_code != 0


def test_ingest_codebase_invalid_path_exits_nonzero(tmp_path: Path) -> None:
    """Passing a non-existent codebase directory exits with non-zero code."""
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])

    result = runner.invoke(
        app,
        [
            "--kb",
            str(kb),
            "ingest",
            "codebase",
            str(tmp_path / "nonexistent"),
            "--name",
            "bad",
        ],
    )
    assert result.exit_code != 0
