"""Tests for the report (collection overview) feature."""

from __future__ import annotations

from pathlib import Path

import frontmatter as fm_lib
from typer.testing import CliRunner

from papermind.cli.main import app
from papermind.report import generate_report

runner = CliRunner()


def _make_kb_with_papers(tmp_path: Path) -> Path:
    """Create a KB with a few test papers."""
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")

    topic_dir = kb / "papers" / "hydrology"

    for i, (title, year, doi, tags) in enumerate(
        [
            (
                "SWAT+ Calibration Guide",
                2020,
                "10.1234/swat2020",
                ["calibration", "swat"],
            ),
            (
                "Green-Ampt Infiltration",
                1911,
                "10.1234/ga1911",
                ["infiltration", "soil"],
            ),
            ("ERA5 Forcing for Models", 2022, "", ["era5", "forcing", "reanalysis"]),
        ]
    ):
        paper_dir = topic_dir / f"paper-{i}"
        paper_dir.mkdir(parents=True)

        post = fm_lib.Post(f"# {title}\n\nContent of paper {i}.\n")
        post.metadata = {
            "type": "paper",
            "id": f"paper-test-{i}",
            "title": title,
            "year": year,
            "doi": doi,
            "topic": "hydrology",
            "tags": tags,
        }
        if i == 0:
            post.metadata["abstract"] = "This paper discusses calibration."
        (paper_dir / "paper.md").write_text(fm_lib.dumps(post))

    return kb


class TestGenerateReport:
    """Test report generation."""

    def test_basic_report(self, tmp_path: Path) -> None:
        kb = _make_kb_with_papers(tmp_path)
        report = generate_report(kb, "hydrology")

        assert "# Report: hydrology" in report
        assert "3 paper(s)" in report
        assert "SWAT+ Calibration Guide" in report
        assert "Green-Ampt Infiltration" in report

    def test_report_inventory_sorted_by_year(self, tmp_path: Path) -> None:
        kb = _make_kb_with_papers(tmp_path)
        report = generate_report(kb, "hydrology")

        # ERA5 (2022) should appear before SWAT (2020) before Green-Ampt (1911)
        idx_era5 = report.index("ERA5")
        idx_swat = report.index("SWAT+")
        idx_ga = report.index("Green-Ampt")
        assert idx_era5 < idx_swat < idx_ga

    def test_report_taxonomy(self, tmp_path: Path) -> None:
        kb = _make_kb_with_papers(tmp_path)
        report = generate_report(kb, "hydrology")

        assert "Keywords" in report
        assert "calibration" in report

    def test_report_coverage(self, tmp_path: Path) -> None:
        kb = _make_kb_with_papers(tmp_path)
        report = generate_report(kb, "hydrology")

        assert "1911" in report  # min year
        assert "2022" in report  # max year
        assert "Missing DOIs:" in report
        assert "1/3" in report

    def test_report_nonexistent_topic(self, tmp_path: Path) -> None:
        kb = _make_kb_with_papers(tmp_path)
        import pytest

        with pytest.raises(FileNotFoundError):
            generate_report(kb, "nonexistent")

    def test_report_empty_topic(self, tmp_path: Path) -> None:
        kb = _make_kb_with_papers(tmp_path)
        empty_dir = kb / "papers" / "empty"
        empty_dir.mkdir(parents=True)

        report = generate_report(kb, "empty")
        assert "No papers found" in report


class TestReportCLI:
    """Test CLI integration."""

    def test_report_cli(self, tmp_path: Path) -> None:
        kb = _make_kb_with_papers(tmp_path)
        result = runner.invoke(app, ["--kb", str(kb), "report", "--topic", "hydrology"])
        assert result.exit_code == 0

    def test_report_cli_save(self, tmp_path: Path) -> None:
        kb = _make_kb_with_papers(tmp_path)
        result = runner.invoke(
            app, ["--kb", str(kb), "report", "--topic", "hydrology", "--save"]
        )
        assert result.exit_code == 0
        assert (kb / "reports" / "hydrology.md").exists()

    def test_report_cli_bad_topic(self, tmp_path: Path) -> None:
        kb = _make_kb_with_papers(tmp_path)
        result = runner.invoke(
            app, ["--kb", str(kb), "report", "--topic", "nonexistent"]
        )
        assert result.exit_code == 1
