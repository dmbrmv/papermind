"""Tests for KB export/import sharing."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import frontmatter as fm_lib
import pytest
from typer.testing import CliRunner

from papermind.catalog.index import CatalogEntry, CatalogIndex
from papermind.cli.main import app
from papermind.sharing import export_kb, import_kb

runner = CliRunner()


def _make_kb(tmp_path: Path, *, with_papers: bool = True) -> Path:
    """Create a KB with test papers."""
    kb = tmp_path / "kb"
    kb.mkdir(parents=True)
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text("[]")

    if not with_papers:
        return kb

    catalog = CatalogIndex(kb)
    for i, (title, topic, doi) in enumerate(
        [
            ("Paper A on Hydrology", "hydrology", "10.1234/a"),
            ("Paper B on Climate", "climate", "10.1234/b"),
            ("Paper C on Hydrology", "hydrology", "10.1234/c"),
        ]
    ):
        paper_dir = kb / "papers" / topic / f"paper-{i}"
        paper_dir.mkdir(parents=True)
        post = fm_lib.Post(f"# {title}\n\nContent.\n")
        post.metadata = {
            "type": "paper",
            "id": f"paper-test-{i}",
            "title": title,
            "topic": topic,
            "doi": doi,
        }
        (paper_dir / "paper.md").write_text(fm_lib.dumps(post))
        (paper_dir / "original.pdf").write_bytes(b"fake-pdf-content")
        catalog.add(
            CatalogEntry(
                id=f"paper-test-{i}",
                type="paper",
                path=f"papers/{topic}/paper-{i}/paper.md",
                title=title,
                topic=topic,
                doi=doi,
            )
        )

    return kb


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_all(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        out = tmp_path / "all.pmkb"
        stats = export_kb(kb, out)
        assert stats["entries"] == 3
        assert stats["files"] > 3  # catalog + 3 paper.md + 3 original.pdf
        assert out.exists()

    def test_export_by_topic(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        out = tmp_path / "hydrology.pmkb"
        stats = export_kb(kb, out, topic="hydrology")
        assert stats["entries"] == 2  # only hydrology papers

    def test_export_by_type(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        out = tmp_path / "papers.pmkb"
        stats = export_kb(kb, out, entry_type="paper")
        assert stats["entries"] == 3

    def test_export_empty_topic(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        out = tmp_path / "empty.pmkb"
        stats = export_kb(kb, out, topic="nonexistent")
        assert stats["entries"] == 0
        assert not out.exists()

    def test_export_contains_catalog(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        out = tmp_path / "test.pmkb"
        export_kb(kb, out)
        with zipfile.ZipFile(out) as zf:
            assert "catalog.json" in zf.namelist()
            data = json.loads(zf.read("catalog.json"))
            assert len(data) == 3

    def test_export_includes_originals(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        out = tmp_path / "test.pmkb"
        export_kb(kb, out)
        with zipfile.ZipFile(out) as zf:
            pdf_files = [n for n in zf.namelist() if n.endswith(".pdf")]
            assert len(pdf_files) == 3


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


class TestImport:
    def test_import_into_empty_kb(self, tmp_path: Path) -> None:
        # Export from source KB
        src_kb = _make_kb(tmp_path / "src")
        archive = tmp_path / "export.pmkb"
        export_kb(src_kb, archive)

        # Import into fresh KB
        dst_kb = _make_kb(tmp_path / "dst", with_papers=False)
        stats = import_kb(dst_kb, archive)
        assert stats["imported"] == 3
        assert stats["skipped"] == 0

        # Verify papers exist
        catalog = CatalogIndex(dst_kb)
        assert len(catalog.entries) == 3

    def test_import_dedup_by_doi(self, tmp_path: Path) -> None:
        src_kb = _make_kb(tmp_path / "src")
        archive = tmp_path / "export.pmkb"
        export_kb(src_kb, archive)

        # Import twice — second should skip all
        dst_kb = _make_kb(tmp_path / "dst", with_papers=False)
        import_kb(dst_kb, archive)
        stats = import_kb(dst_kb, archive)
        assert stats["imported"] == 0
        assert stats["skipped"] == 3

    def test_import_no_merge_overwrites(self, tmp_path: Path) -> None:
        src_kb = _make_kb(tmp_path / "src")
        archive = tmp_path / "export.pmkb"
        export_kb(src_kb, archive)

        dst_kb = _make_kb(tmp_path / "dst", with_papers=False)
        import_kb(dst_kb, archive)
        # With merge=False, should import again (replace)
        stats = import_kb(dst_kb, archive, merge=False)
        assert stats["imported"] == 3

    def test_import_corrupt_archive(self, tmp_path: Path) -> None:
        dst_kb = _make_kb(tmp_path / "dst", with_papers=False)
        bad_archive = tmp_path / "bad.pmkb"
        bad_archive.write_bytes(b"not a zip file")
        with pytest.raises(Exception):
            import_kb(dst_kb, bad_archive)

    def test_import_missing_catalog(self, tmp_path: Path) -> None:
        dst_kb = _make_kb(tmp_path / "dst", with_papers=False)
        bad_archive = tmp_path / "empty.pmkb"
        with zipfile.ZipFile(bad_archive, "w") as zf:
            zf.writestr("dummy.txt", "nothing here")
        stats = import_kb(dst_kb, bad_archive)
        assert stats["imported"] == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestSharingCLI:
    def test_export_cli(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path)
        out = tmp_path / "cli-export.pmkb"
        result = runner.invoke(
            app,
            ["--kb", str(kb), "export", "-o", str(out), "--topic", "hydrology"],
        )
        assert result.exit_code == 0
        assert "Exported" in result.output
        assert "2 entries" in result.output

    def test_import_cli(self, tmp_path: Path) -> None:
        src_kb = _make_kb(tmp_path / "src")
        archive = tmp_path / "cli.pmkb"
        export_kb(src_kb, archive)

        dst_kb = _make_kb(tmp_path / "dst", with_papers=False)
        result = runner.invoke(app, ["--kb", str(dst_kb), "import", str(archive)])
        assert result.exit_code == 0
        assert "Imported" in result.output

    def test_import_cli_missing_file(self, tmp_path: Path) -> None:
        kb = _make_kb(tmp_path, with_papers=False)
        result = runner.invoke(
            app, ["--kb", str(kb), "import", str(tmp_path / "nonexistent.pmkb")]
        )
        assert result.exit_code == 1
