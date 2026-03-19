"""Tests for project profile generation."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from papermind.cli.main import app
from papermind.profile import format_profile, generate_profile

runner = CliRunner()


def _make_codebase(tmp_path: Path) -> Path:
    """Create a sample codebase with Python and Fortran files."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("# My Project\n\nA scientific model.\n")

    src = root / "src"
    src.mkdir()
    (src / "model.py").write_text(
        "# REF: doi:10.1234/model-paper eq.1\n"
        "def compute_runoff(precip, cn):\n"
        '    """Compute surface runoff using SCS-CN."""\n'
        "    return precip * cn\n\n"
        "class WaterBalance:\n"
        "    pass\n"
    )
    (src / "utils.py").write_text(
        "def load_data(path):\n    pass\n\ndef save_results(data):\n    pass\n"
    )

    fortran = root / "lib"
    fortran.mkdir()
    (fortran / "solver.f90").write_text(
        "! REF: doi:10.5678/solver-paper\n"
        "subroutine solve_flow(q, dt)\n"
        "  real :: q, dt\n"
        "end subroutine\n"
    )

    return root


class TestGenerateProfile:
    """Test profile generation."""

    def test_basic_profile(self, tmp_path: Path) -> None:
        root = _make_codebase(tmp_path)
        profile = generate_profile(root)

        assert profile.name == "project"
        assert "python" in profile.languages
        assert "fortran" in profile.languages
        assert profile.function_count >= 3  # compute_runoff, load_data, save_results
        assert profile.class_count >= 1  # WaterBalance

    def test_profile_linked_papers(self, tmp_path: Path) -> None:
        root = _make_codebase(tmp_path)
        profile = generate_profile(root)

        assert len(profile.linked_papers) == 2
        assert "10.1234/model-paper" in profile.linked_papers
        assert "10.5678/solver-paper" in profile.linked_papers

    def test_profile_readme_excerpt(self, tmp_path: Path) -> None:
        root = _make_codebase(tmp_path)
        profile = generate_profile(root)

        assert "My Project" in profile.readme_excerpt

    def test_profile_key_topics(self, tmp_path: Path) -> None:
        root = _make_codebase(tmp_path)
        profile = generate_profile(root)

        # Should infer topics from function names
        assert isinstance(profile.key_topics, list)

    def test_profile_empty_codebase(self, tmp_path: Path) -> None:
        root = tmp_path / "empty"
        root.mkdir()

        profile = generate_profile(root)
        assert profile.file_count == 0
        assert profile.function_count == 0
        assert profile.linked_papers == []

    def test_profile_no_annotations(self, tmp_path: Path) -> None:
        root = tmp_path / "clean"
        root.mkdir()
        (root / "main.py").write_text("def hello():\n    print('hi')\n")

        profile = generate_profile(root)
        assert profile.linked_papers == []
        assert profile.function_count == 1


class TestFormatProfile:
    """Test profile formatting."""

    def test_format_basic(self, tmp_path: Path) -> None:
        root = _make_codebase(tmp_path)
        profile = generate_profile(root)
        text = format_profile(profile)

        assert "Project Profile:" in text
        assert "python" in text.lower()
        assert "Paper References" in text


class TestProfileCLI:
    """Test CLI integration."""

    def test_profile_cli(self, tmp_path: Path) -> None:
        root = _make_codebase(tmp_path)
        result = runner.invoke(app, ["profile", str(root)])
        assert result.exit_code == 0
        assert "Project Profile" in result.output

    def test_profile_cli_bad_path(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["profile", str(tmp_path / "nonexistent")])
        assert result.exit_code == 1
