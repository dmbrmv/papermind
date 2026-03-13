"""Tests for config loading."""

from __future__ import annotations

from pathlib import Path

import pytest
from hydrofound.config import load_config


def test_default_config_values(tmp_path: Path) -> None:
    """Config has sensible defaults when no file exists."""
    cfg = load_config(tmp_path)
    assert cfg.base_path == tmp_path
    assert cfg.marker_path == "marker"
    assert cfg.qmd_path == "qmd"
    assert cfg.marker_use_llm is False
    assert cfg.offline_only is False
    assert cfg.default_paper_topic == "uncategorized"


def test_env_vars_override_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment variables take precedence over config.toml."""
    monkeypatch.setenv("HYDROFOUND_EXA_KEY", "test-exa-key")
    monkeypatch.setenv("HYDROFOUND_SEMANTIC_SCHOLAR_KEY", "test-scholar-key")
    cfg = load_config(tmp_path)
    assert cfg.exa_key == "test-exa-key"
    assert cfg.semantic_scholar_key == "test-scholar-key"


def test_config_from_toml(tmp_path: Path) -> None:
    """Config loads values from .hydrofound/config.toml."""
    config_dir = tmp_path / ".hydrofound"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[ingestion]\nmarker_path = "/usr/local/bin/marker"\ndefault_paper_topic = "hydrology"\n'
    )
    cfg = load_config(tmp_path)
    assert cfg.marker_path == "/usr/local/bin/marker"
    assert cfg.default_paper_topic == "hydrology"


def test_env_vars_override_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Env vars win over toml values."""
    config_dir = tmp_path / ".hydrofound"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text('[apis]\nexa_key = "from-file"\n')
    monkeypatch.setenv("HYDROFOUND_EXA_KEY", "from-env")
    cfg = load_config(tmp_path)
    assert cfg.exa_key == "from-env"
