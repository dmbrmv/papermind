"""Tests for config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from papermind.config import load_config


def test_default_config_values(tmp_path: Path) -> None:
    """Config has sensible defaults when no file exists."""
    cfg = load_config(tmp_path)
    assert cfg.base_path == tmp_path
    assert cfg.qmd_path == "qmd"
    assert cfg.ocr_model == "zai-org/GLM-OCR"
    assert cfg.ocr_dpi == 150
    assert cfg.offline_only is False
    assert cfg.default_paper_topic == "uncategorized"


def test_env_vars_override_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment variables take precedence over config.toml."""
    monkeypatch.setenv("PAPERMIND_EXA_KEY", "test-exa-key")
    monkeypatch.setenv("PAPERMIND_SEMANTIC_SCHOLAR_KEY", "test-scholar-key")
    cfg = load_config(tmp_path)
    assert cfg.exa_key == "test-exa-key"
    assert cfg.semantic_scholar_key == "test-scholar-key"


def test_config_from_toml(tmp_path: Path) -> None:
    """Config loads values from .papermind/config.toml."""
    config_dir = tmp_path / ".papermind"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[ingestion]\nocr_dpi = 300\ndefault_paper_topic = "hydrology"\n'
    )
    cfg = load_config(tmp_path)
    assert cfg.ocr_dpi == 300
    assert cfg.default_paper_topic == "hydrology"


def test_env_vars_override_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Env vars win over toml values."""
    config_dir = tmp_path / ".papermind"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text('[apis]\nexa_key = "from-file"\n')
    monkeypatch.setenv("PAPERMIND_EXA_KEY", "from-env")
    cfg = load_config(tmp_path)
    assert cfg.exa_key == "from-env"


# ===========================================================================
# E2: Batch C config tests
# ===========================================================================


def test_config_warns_unknown_section(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Unknown top-level section in config.toml triggers a warning log."""
    config_dir = tmp_path / ".papermind"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[ingestion]\nocr_dpi = 150\n\n[unknown_stuff]\nfoo = 42\n"
    )
    with caplog.at_level("WARNING", logger="papermind.config"):
        load_config(tmp_path)

    assert any("unknown_stuff" in record.message for record in caplog.records)


def test_config_clamps_low_dpi(tmp_path: Path) -> None:
    """ocr_dpi below 72 is clamped to 72."""
    config_dir = tmp_path / ".papermind"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("[ingestion]\nocr_dpi = 10\n")
    cfg = load_config(tmp_path)
    assert cfg.ocr_dpi == 72


def test_config_clamps_high_dpi(tmp_path: Path) -> None:
    """ocr_dpi above 600 is clamped to 600."""
    config_dir = tmp_path / ".papermind"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("[ingestion]\nocr_dpi = 9999\n")
    cfg = load_config(tmp_path)
    assert cfg.ocr_dpi == 600
