"""Tests for implementation verification."""

from __future__ import annotations

from pathlib import Path

import frontmatter as fm_lib
from typer.testing import CliRunner

from papermind.cli.main import app
from papermind.verify import format_verification, verify_implementation

runner = CliRunner()


def _make_kb_with_equation(tmp_path: Path) -> Path:
    """Create a KB with a paper that has equations in frontmatter."""
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")

    paper_dir = kb / "papers" / "hydrology" / "scs-cn"
    paper_dir.mkdir(parents=True)

    post = fm_lib.Post("# SCS Curve Number Method\n\nContent.\n")
    post.metadata = {
        "type": "paper",
        "id": "paper-scs-cn-1986",
        "title": "SCS Curve Number Method",
        "topic": "hydrology",
        "equations": [
            {
                "latex": "Q = \\frac{(P - I_a)^2}{(P - I_a) + S}",
                "number": "2.1",
                "display": True,
                "section": "Methods",
            },
        ],
    }
    (paper_dir / "paper.md").write_text(fm_lib.dumps(post))

    # Also add to catalog
    from papermind.catalog.index import CatalogEntry, CatalogIndex

    catalog = CatalogIndex(kb)
    catalog.add(
        CatalogEntry(
            id="paper-scs-cn-1986",
            type="paper",
            path="papers/hydrology/scs-cn/paper.md",
            title="SCS Curve Number Method",
            topic="hydrology",
        )
    )

    return kb


class TestVerifyImplementation:
    """Test the verification orchestrator."""

    def test_verify_with_matching_code(self, tmp_path: Path) -> None:
        kb = _make_kb_with_equation(tmp_path)
        src = tmp_path / "model.py"
        src.write_text(
            "def calc_runoff(P, S, I_a):\n"
            "    Q = (P - I_a) ** 2 / ((P - I_a) + S)\n"
            "    return Q\n"
        )

        result = verify_implementation(
            "paper-scs-cn-1986", "2.1", src, "calc_runoff", kb
        )

        assert result.verdict in ("good", "partial")
        assert result.coverage > 0
        assert len(result.mappings) > 0

    def test_verify_equation_not_found(self, tmp_path: Path) -> None:
        kb = _make_kb_with_equation(tmp_path)
        src = tmp_path / "model.py"
        src.write_text("def f(): pass\n")

        result = verify_implementation("paper-scs-cn-1986", "99.9", src, None, kb)
        assert result.verdict == "no_data"

    def test_verify_paper_not_found(self, tmp_path: Path) -> None:
        kb = _make_kb_with_equation(tmp_path)
        src = tmp_path / "model.py"
        src.write_text("def f(): pass\n")

        result = verify_implementation("paper-nonexistent", "1.0", src, None, kb)
        assert result.verdict == "no_data"

    def test_verify_with_provenance(self, tmp_path: Path) -> None:
        """Provenance annotations in the file are included in report."""
        kb = _make_kb_with_equation(tmp_path)
        src = tmp_path / "model.py"
        src.write_text(
            "# REF: doi:10.1234/scs eq.2.1\n"
            "def calc_runoff(P, S):\n"
            "    return (P ** 2) / (P + S)\n"
        )

        result = verify_implementation(
            "paper-scs-cn-1986", "2.1", src, "calc_runoff", kb
        )
        assert len(result.provenance_refs) > 0


class TestFormatVerification:
    """Test output formatting."""

    def test_format_good(self, tmp_path: Path) -> None:
        kb = _make_kb_with_equation(tmp_path)
        src = tmp_path / "model.py"
        src.write_text("def f(P, S, Q): Q = P / S\n")

        result = verify_implementation("paper-scs-cn-1986", "2.1", src, None, kb)
        text = format_verification(result)
        assert "Verification" in text
        assert "SCS Curve Number" in text


class TestVerifyCLI:
    """Test CLI command."""

    def test_verify_cli(self, tmp_path: Path) -> None:
        kb = _make_kb_with_equation(tmp_path)
        src = tmp_path / "model.py"
        src.write_text("def calc(P, S, Q):\n    Q = P / S\n")

        result = runner.invoke(
            app,
            [
                "--kb",
                str(kb),
                "verify",
                str(src),
                "--paper",
                "paper-scs-cn-1986",
                "--eq",
                "2.1",
            ],
        )
        # May exit 0 or 1 depending on verdict, just check it runs
        assert result.exit_code in (0, 1)
        assert "Verification" in result.output
