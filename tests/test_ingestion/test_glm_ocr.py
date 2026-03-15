"""Tests for GLM-OCR converter module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from hydrofound.cli.main import app
from hydrofound.ingestion.glm_ocr import is_available

runner = CliRunner()


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


def test_is_available_returns_bool() -> None:
    """is_available returns a boolean (True if deps installed, False otherwise)."""
    result = is_available()
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# convert_pdf dispatch
# ---------------------------------------------------------------------------


def test_convert_pdf_dispatches_to_glm(tmp_path: Path) -> None:
    """convert_pdf routes to GLM-OCR when config.converter == 'glm-ocr'."""
    from hydrofound.config import HydroFoundConfig

    config = HydroFoundConfig(base_path=tmp_path, converter="glm-ocr")

    with patch(
        "hydrofound.ingestion.paper._convert_pdf_glm",
        return_value="# GLM output",
    ) as mock_glm:
        from hydrofound.ingestion.paper import convert_pdf

        result = convert_pdf(tmp_path / "test.pdf", config)

    mock_glm.assert_called_once()
    assert result == "# GLM output"


def test_convert_pdf_dispatches_to_marker(tmp_path: Path) -> None:
    """convert_pdf routes to Marker when config.converter == 'marker'."""
    from hydrofound.config import HydroFoundConfig

    config = HydroFoundConfig(base_path=tmp_path, converter="marker")

    with patch(
        "hydrofound.ingestion.paper._convert_pdf_marker",
        return_value="# Marker output",
    ) as mock_marker:
        from hydrofound.ingestion.paper import convert_pdf

        result = convert_pdf(tmp_path / "test.pdf", config)

    mock_marker.assert_called_once()
    assert result == "# Marker output"


# ---------------------------------------------------------------------------
# convert_pdf_glm with mocked model
# ---------------------------------------------------------------------------


def test_convert_pdf_glm_produces_markdown(tmp_path: Path) -> None:
    """GLM converter produces markdown from a PDF (fully mocked)."""
    # Create a fake PDF
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 2000)

    # Mock the entire chain: pymupdf rendering + model inference
    fake_image = MagicMock()
    fake_image.width = 100
    fake_image.height = 100

    with (
        patch("hydrofound.ingestion.glm_ocr.is_available", return_value=True),
        patch("hydrofound.ingestion.glm_ocr._render_pdf_pages") as mock_render,
        patch("hydrofound.ingestion.glm_ocr._ensure_model") as mock_model,
        patch("hydrofound.ingestion.glm_ocr._ocr_image") as mock_ocr,
    ):
        mock_render.return_value = [fake_image, fake_image]  # 2 pages
        mock_model.return_value = (MagicMock(), MagicMock())
        mock_ocr.side_effect = [
            "# Page 1\n\nFirst page content.",
            "# Page 2\n\nSecond page content.",
        ]

        from hydrofound.ingestion.glm_ocr import convert_pdf_glm

        result = convert_pdf_glm(pdf, model_name="test-model", dpi=72)

    assert "Page 1" in result
    assert "Page 2" in result
    assert "---" in result  # Page separator
    assert mock_ocr.call_count == 2


def test_convert_pdf_glm_raises_when_deps_missing(tmp_path: Path) -> None:
    """GLM converter raises ImportError when deps not installed."""
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 2000)

    with patch("hydrofound.ingestion.glm_ocr.is_available", return_value=False):
        from hydrofound.ingestion.glm_ocr import convert_pdf_glm

        with pytest.raises(ImportError, match="hydrofound\\[ocr\\]"):
            convert_pdf_glm(pdf)


# ---------------------------------------------------------------------------
# CLI paper ingest with GLM-OCR mock
# ---------------------------------------------------------------------------


def _init_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    result = runner.invoke(app, ["init", str(kb)])
    assert result.exit_code == 0, result.output
    return kb


def _make_fake_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4\n" + b"x" * 2000)
    return path


def test_cli_paper_ingest_uses_glm_by_default(tmp_path: Path) -> None:
    """CLI ingest paper uses GLM-OCR by default (not marker)."""
    kb = _init_kb(tmp_path)
    pdf = _make_fake_pdf(tmp_path / "paper.pdf")

    markdown_output = (
        "# A Research Paper\n\n"
        "Some content about hydrology (2024).\n\n"
        "DOI: 10.1234/test-glm-ocr\n"
    )

    with patch(
        "hydrofound.ingestion.paper._convert_pdf_glm",
        return_value=markdown_output,
    ):
        result = runner.invoke(
            app,
            ["--kb", str(kb), "ingest", "paper", str(pdf), "--topic", "test"],
        )

    assert result.exit_code == 0, result.output
    assert "research paper" in result.output.lower()


def test_cli_paper_ingest_falls_back_to_marker(tmp_path: Path) -> None:
    """When config has converter=marker, the marker path is used."""
    kb = _init_kb(tmp_path)
    pdf = _make_fake_pdf(tmp_path / "paper.pdf")

    # Write config with marker converter
    config_path = kb / ".hydrofound" / "config.toml"
    config_text = config_path.read_text()
    config_path.write_text(
        config_text.replace('converter = "glm-ocr"', 'converter = "marker"')
    )

    original_run = subprocess.run

    def fake_marker(cmd, **kwargs):
        if cmd[0] == "marker":
            input_path = Path(cmd[1])
            output_dir = input_path.parent / input_path.stem
            output_dir.mkdir(exist_ok=True)
            (output_dir / f"{input_path.stem}.md").write_text(
                "# Marker Output\n\nContent (2024).\n"
            )
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return original_run(cmd, **kwargs)

    with patch("subprocess.run", side_effect=fake_marker):
        result = runner.invoke(
            app,
            ["--kb", str(kb), "ingest", "paper", str(pdf), "--topic", "test"],
        )

    assert result.exit_code == 0, result.output
    assert "marker" in result.output.lower()


# ---------------------------------------------------------------------------
# Config fields
# ---------------------------------------------------------------------------


def test_config_has_converter_fields() -> None:
    """HydroFoundConfig has the new converter fields with correct defaults."""
    from hydrofound.config import HydroFoundConfig

    cfg = HydroFoundConfig(base_path=Path("/tmp"))
    assert cfg.converter == "glm-ocr"
    assert cfg.ocr_model == "zai-org/GLM-OCR"
    assert cfg.ocr_dpi == 150
