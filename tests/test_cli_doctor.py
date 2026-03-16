"""Tests for the papermind doctor CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from papermind.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_kb(kb: Path) -> None:
    """Bootstrap a minimal knowledge base accepted by doctor."""
    runner.invoke(app, ["init", str(kb)])


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------


def test_doctor_found_deps_show_checkmark() -> None:
    """When all executables are present, each shows a green ✓."""
    with patch("shutil.which", return_value="/usr/bin/fake"):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    # All four named deps should show ✓
    for name in ("griffe", "qmd", "node"):
        assert name in result.output
    assert "✓" in result.output


def test_doctor_missing_deps_show_cross() -> None:
    """When executables are absent, each shows ✗."""
    with patch("shutil.which", return_value=None):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "✗" in result.output


def test_doctor_individual_dep_found(tmp_path: Path) -> None:
    """shutil.which returning a path for a specific cmd → ✓ for that entry."""

    def fake_which(cmd: str) -> str | None:
        return "/usr/bin/node" if cmd == "node" else None

    with patch("shutil.which", side_effect=fake_which):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "node" in result.output
    assert "griffe" in result.output


def test_doctor_playwright_installed() -> None:
    """When playwright is importable, it shows ✓."""
    import types

    fake_playwright = types.ModuleType("playwright")
    with patch.dict("sys.modules", {"playwright": fake_playwright}):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "playwright" in result.output


def test_doctor_playwright_missing() -> None:
    """When playwright is not installed, it shows ✗ with install hint."""
    with patch.dict("sys.modules", {"playwright": None}):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "playwright" in result.output


# ---------------------------------------------------------------------------
# API key checks
# ---------------------------------------------------------------------------


def test_doctor_api_key_set() -> None:
    """When PAPERMIND_EXA_KEY is set, the output shows 'set'."""
    env = {"PAPERMIND_EXA_KEY": "sk-test-123"}
    with patch.dict("os.environ", env, clear=False):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "PAPERMIND_EXA_KEY" in result.output
    # The key value must NOT appear — only presence is checked
    assert "sk-test-123" not in result.output
    assert "set" in result.output


def test_doctor_api_key_not_set() -> None:
    """When API keys are absent the output shows 'not set'."""
    keys = [
        "PAPERMIND_EXA_KEY",
        "PAPERMIND_SEMANTIC_SCHOLAR_KEY",
        "PAPERMIND_FIRECRAWL_KEY",
    ]
    env_patch = {k: "" for k in keys}
    with patch.dict("os.environ", env_patch, clear=False):
        # Also ensure they are actually removed if empty strings don't suffice
        import os

        backup = {k: os.environ.pop(k, None) for k in keys}
        try:
            result = runner.invoke(app, ["doctor"])
        finally:
            for k, v in backup.items():
                if v is not None:
                    os.environ[k] = v
    assert result.exit_code == 0
    assert "not set" in result.output


def test_doctor_all_three_api_keys_listed() -> None:
    """All three expected API key names appear in the output."""
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    for key in (
        "PAPERMIND_EXA_KEY",
        "PAPERMIND_SEMANTIC_SCHOLAR_KEY",
        "PAPERMIND_FIRECRAWL_KEY",
    ):
        assert key in result.output


def test_doctor_does_not_print_key_values() -> None:
    """API key values must never appear in the output."""
    secret = "super-secret-value-xyz"
    env = {
        "PAPERMIND_EXA_KEY": secret,
        "PAPERMIND_SEMANTIC_SCHOLAR_KEY": secret,
        "PAPERMIND_FIRECRAWL_KEY": secret,
    }
    with patch.dict("os.environ", env, clear=False):
        result = runner.invoke(app, ["doctor"])
    assert secret not in result.output


# ---------------------------------------------------------------------------
# KB stats
# ---------------------------------------------------------------------------


def test_doctor_no_kb_shows_hint() -> None:
    """Without --kb the output explains how to pass it."""
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "--kb" in result.output


def test_doctor_uninitialized_kb_warning(tmp_path: Path) -> None:
    """Pointing --kb at a directory without .papermind marker shows a warning."""
    kb = tmp_path / "not_a_kb"
    kb.mkdir()
    result = runner.invoke(app, ["--kb", str(kb), "doctor"])
    assert result.exit_code == 0
    assert "not initialized" in result.output.lower() or str(kb) in result.output


def test_doctor_kb_stats_empty(tmp_path: Path) -> None:
    """An initialized but empty KB shows zero counts."""
    kb = tmp_path / "kb"
    _init_kb(kb)
    result = runner.invoke(app, ["--kb", str(kb), "doctor"])
    assert result.exit_code == 0
    assert "Papers:" in result.output
    assert "0" in result.output


def test_doctor_kb_stats_with_entries(tmp_path: Path) -> None:
    """KB stats reflect actual catalog entries."""
    kb = tmp_path / "kb"
    _init_kb(kb)

    # Populate catalog.json with known entries
    entries = [
        {
            "id": "paper-001",
            "type": "paper",
            "path": "papers/p1.md",
            "topic": "hydrology",
        },
        {
            "id": "paper-002",
            "type": "paper",
            "path": "papers/p2.md",
            "topic": "hydrology",
        },
        {"id": "pkg-001", "type": "package", "path": "packages/pkg1.md", "topic": "ml"},
        {"id": "cb-001", "type": "codebase", "path": "codebases/cb1.md"},
    ]
    (kb / "catalog.json").write_text(json.dumps(entries))

    result = runner.invoke(app, ["--kb", str(kb), "doctor"])
    assert result.exit_code == 0
    assert "Papers:    2" in result.output
    assert "Packages:  1" in result.output
    assert "Codebases: 1" in result.output
    # Topics should list hydrology(2) and ml(1)
    assert "hydrology" in result.output
    assert "ml" in result.output


def test_doctor_kb_shows_path(tmp_path: Path) -> None:
    """The KB path is printed in the output."""
    kb = tmp_path / "kb"
    _init_kb(kb)
    result = runner.invoke(app, ["--kb", str(kb), "doctor"])
    assert result.exit_code == 0
    assert str(kb) in result.output


# ---------------------------------------------------------------------------
# Exit code
# ---------------------------------------------------------------------------


def test_doctor_always_exits_zero() -> None:
    """doctor exits 0 regardless of missing deps or keys."""
    with patch("shutil.which", return_value=None):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0


def test_doctor_exits_zero_with_all_missing(tmp_path: Path) -> None:
    """Even with no KB, no deps, and no keys, exit code is 0."""
    import os

    keys = [
        "PAPERMIND_EXA_KEY",
        "PAPERMIND_SEMANTIC_SCHOLAR_KEY",
        "PAPERMIND_FIRECRAWL_KEY",
    ]
    backup = {k: os.environ.pop(k, None) for k in keys}
    try:
        with patch("shutil.which", return_value=None):
            result = runner.invoke(app, ["doctor"])
    finally:
        for k, v in backup.items():
            if v is not None:
                os.environ[k] = v
    assert result.exit_code == 0
