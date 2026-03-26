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
    assert cfg.ocr_backend == "local"
    assert cfg.ocr_model == "zai-org/GLM-OCR"
    assert cfg.ocr_dpi == 150
    assert cfg.ocr_max_new_tokens == 4096
    assert cfg.extract_pdf_images is True
    assert cfg.recovery_ocr_dpi == 120
    assert cfg.recovery_ocr_max_new_tokens == 3072
    assert cfg.recovery_max_pdf_pages == 20
    assert cfg.recovery_ocr_timeout_seconds == 180
    assert cfg.zai_base_url == "https://api.z.ai/api/paas/v4"
    assert cfg.zai_model == "glm-ocr"
    assert cfg.zai_timeout_seconds == 120
    assert cfg.zai_max_pages == 40
    assert cfg.offline_only is False
    assert cfg.default_paper_topic == "uncategorized"


def test_env_vars_override_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment variables take precedence over config.toml."""
    monkeypatch.setenv("PAPERMIND_EXA_KEY", "test-exa-key")
    monkeypatch.setenv("PAPERMIND_SEMANTIC_SCHOLAR_KEY", "test-scholar-key")
    monkeypatch.setenv("PAPERMIND_ZAI_API_KEY", "test-zai-key")
    cfg = load_config(tmp_path)
    assert cfg.exa_key == "test-exa-key"
    assert cfg.semantic_scholar_key == "test-scholar-key"
    assert cfg.zai_api_key == "test-zai-key"


def test_config_from_toml(tmp_path: Path) -> None:
    """Config loads values from .papermind/config.toml."""
    config_dir = tmp_path / ".papermind"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[ingestion]\n"
        'ocr_backend = "zai"\n'
        "ocr_dpi = 300\n"
        "ocr_max_new_tokens = 5000\n"
        "extract_pdf_images = false\n"
        'default_paper_topic = "hydrology"\n'
        "recovery_ocr_dpi = 96\n"
        "recovery_ocr_max_new_tokens = 2500\n"
        "recovery_max_pdf_pages = 12\n"
        "recovery_ocr_timeout_seconds = 45\n"
        'zai_base_url = "https://example.invalid/api"\n'
        'zai_model = "glm-ocr"\n'
        "zai_timeout_seconds = 75\n"
        "zai_max_pages = 15\n"
    )
    cfg = load_config(tmp_path)
    assert cfg.ocr_backend == "zai"
    assert cfg.ocr_dpi == 300
    assert cfg.ocr_max_new_tokens == 5000
    assert cfg.extract_pdf_images is False
    assert cfg.default_paper_topic == "hydrology"
    assert cfg.recovery_ocr_dpi == 96
    assert cfg.recovery_ocr_max_new_tokens == 2500
    assert cfg.recovery_max_pdf_pages == 12
    assert cfg.recovery_ocr_timeout_seconds == 45
    assert cfg.zai_base_url == "https://example.invalid/api"
    assert cfg.zai_model == "glm-ocr"
    assert cfg.zai_timeout_seconds == 75
    assert cfg.zai_max_pages == 15


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


def test_config_invalid_ocr_backend_defaults_to_local(tmp_path: Path) -> None:
    """Invalid OCR backend value falls back to local."""
    config_dir = tmp_path / ".papermind"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text('[ingestion]\nocr_backend = "weird"\n')
    cfg = load_config(tmp_path)
    assert cfg.ocr_backend == "local"
