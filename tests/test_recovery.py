"""Tests for deleted-paper recovery runtime bounds and quarantine output."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from papermind.config import PaperMindConfig
import json

from papermind.recovery import _recover_one_item, run_deleted_paper_recovery


class _FakeCandidate:
    def __init__(self, title: str, doi: str, year: int, pdf_url: str) -> None:
        self.title = title
        self.doi = doi
        self.year = year
        self.pdf_url = pdf_url
        self.abstract = ""
        self.cites = []
        self.cited_by = []


class _FakeProvider:
    pass


def test_recover_one_item_fails_on_page_limit(tmp_path: Path) -> None:
    """Recovery should fail fast when PDF exceeds the configured page limit."""
    kb = tmp_path / "kb"
    kb.mkdir()
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    pdf_path = pdf_dir / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    log_path = tmp_path / "recovery.log"

    config = PaperMindConfig(
        base_path=kb,
        recovery_max_pdf_pages=1,
        recovery_ocr_timeout_seconds=180,
    )
    item = {"title": "Test Paper", "topic": "hydrology", "path": "papers/x/paper.md", "paper_id": "paper-x"}
    candidate = _FakeCandidate("Test Paper", "10.1234/test", 2024, "https://example.com/paper.pdf")

    with (
        patch("papermind.recovery._choose_candidate", return_value=(candidate, 1.0)),
        patch("papermind.recovery.download_paper", return_value=pdf_path),
        patch("papermind.recovery._pdf_page_count", return_value=5),
    ):
        result = _recover_one_item(
            kb,
            pdf_dir,
            config,
            _FakeProvider(),
            item,
            min_similarity=0.9,
            log_path=log_path,
        )

    assert result["bucket"] == "failed"
    assert result["record"]["reason"] == "page_limit_exceeded"


def test_recover_one_item_fails_on_ocr_timeout(tmp_path: Path) -> None:
    """Recovery should classify OCR timeouts explicitly."""
    kb = tmp_path / "kb"
    kb.mkdir()
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    pdf_path = pdf_dir / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    log_path = tmp_path / "recovery.log"

    config = PaperMindConfig(
        base_path=kb,
        recovery_max_pdf_pages=20,
        recovery_ocr_timeout_seconds=1,
    )
    item = {"title": "Timeout Paper", "topic": "hydrology", "path": "papers/x/paper.md", "paper_id": "paper-x"}
    candidate = _FakeCandidate("Timeout Paper", "10.1234/timeout", 2024, "https://example.com/paper.pdf")

    with (
        patch("papermind.recovery._choose_candidate", return_value=(candidate, 1.0)),
        patch("papermind.recovery.download_paper", return_value=pdf_path),
        patch("papermind.recovery._pdf_page_count", return_value=2),
        patch("papermind.recovery.ingest_paper", side_effect=TimeoutError("Recovery OCR timed out")),
    ):
        result = _recover_one_item(
            kb,
            pdf_dir,
            config,
            _FakeProvider(),
            item,
            min_similarity=0.9,
            log_path=log_path,
        )

    assert result["bucket"] == "failed"
    assert result["record"]["reason"] == "ocr_timeout"


def test_run_deleted_paper_recovery_writes_quarantine_artifact(tmp_path: Path) -> None:
    """Non-restored recovery outcomes should produce quarantine artifacts."""
    kb = tmp_path / "kb"
    (kb / ".papermind" / "recovery").mkdir(parents=True)
    report = kb / ".papermind" / "reports" / "report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "title": "Quarantine Paper",
                        "path": "papers/hydrology/quarantine-paper/paper.md",
                        "paper_id": "paper-quarantine",
                    }
                ]
            }
        )
    )

    fake_result = {
        "bucket": "failed",
        "record": {
            "title": "Quarantine Paper",
            "topic": "hydrology",
            "requested_path": "papers/hydrology/quarantine-paper/paper.md",
            "requested_paper_id": "paper-quarantine",
            "reason": "download_failed",
        },
    }

    with patch("papermind.recovery._recover_one_item", return_value=fake_result):
        run_deleted_paper_recovery(kb, report, max_items=1)

    artifact = (
        kb
        / ".papermind"
        / "recovery"
        / "quarantine"
        / "quarantine-paper.download_failed.json"
    )
    assert artifact.exists()


def test_run_deleted_paper_recovery_writes_intake_artifact(tmp_path: Path) -> None:
    """Restored recovery outcomes should produce intake artifacts."""
    kb = tmp_path / "kb"
    (kb / ".papermind" / "recovery").mkdir(parents=True)
    report = kb / ".papermind" / "reports" / "report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "title": "Restored Paper",
                        "path": "papers/hydrology/restored-paper/paper.md",
                        "paper_id": "paper-restored",
                    }
                ]
            }
        )
    )

    fake_result = {
        "bucket": "restored",
        "record": {
            "title": "Restored Paper",
            "topic": "hydrology",
            "requested_path": "papers/hydrology/restored-paper/paper.md",
            "requested_paper_id": "paper-restored",
            "reason": "restored",
            "entry_id": "paper-restored-2024",
            "doi": "10.1234/restored",
            "intake_ok": True,
        },
    }

    with patch("papermind.recovery._recover_one_item", return_value=fake_result):
        run_deleted_paper_recovery(kb, report, max_items=1)

    artifact = (
        kb
        / ".papermind"
        / "recovery"
        / "intake"
        / "restored-paper.restored.json"
    )
    assert artifact.exists()


def test_mark_recovered_paper_verified_updates_frontmatter(tmp_path: Path) -> None:
    """Restored papers should be stamped with verification metadata."""
    import frontmatter

    from papermind.recovery import _mark_recovered_paper_verified

    kb = tmp_path / "kb"
    paper_dir = kb / "papers" / "hydrology" / "restored-paper"
    paper_dir.mkdir(parents=True)
    (kb / ".papermind").mkdir()
    (kb / "catalog.json").write_text(
        json.dumps(
            [
                {
                    "id": "paper-restored-2024",
                    "type": "paper",
                    "title": "Restored Paper",
                    "path": "papers/hydrology/restored-paper/paper.md",
                    "topic": "hydrology",
                }
            ]
        )
    )

    post = frontmatter.Post("# Restored Paper")
    post.metadata = {"type": "paper", "id": "paper-restored-2024", "title": "Restored Paper", "topic": "hydrology"}
    paper_path = paper_dir / "paper.md"
    paper_path.write_text(frontmatter.dumps(post))

    _mark_recovered_paper_verified(kb, "paper-restored-2024")

    updated = frontmatter.load(paper_path)
    assert updated.metadata["last_verified"]
    assert updated.metadata["verification_note"] == "recovery_intake_passed"


def test_recovery_resume_processes_remaining_pending(tmp_path: Path) -> None:
    """A second recovery run should continue from the saved pending queue."""
    kb = tmp_path / "kb"
    (kb / ".papermind" / "recovery").mkdir(parents=True)
    report = kb / ".papermind" / "reports" / "report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "findings": [
                    {"title": "Paper One", "path": "papers/hydrology/paper-one/paper.md", "paper_id": "paper-one"},
                    {"title": "Paper Two", "path": "papers/hydrology/paper-two/paper.md", "paper_id": "paper-two"},
                ]
            }
        )
    )

    results = iter(
        [
            {"bucket": "restored", "record": {"title": "Paper One", "topic": "hydrology", "reason": "restored"}},
            {"bucket": "skipped", "record": {"title": "Paper Two", "topic": "hydrology", "reason": "doi_already_present"}},
        ]
    )

    with patch("papermind.recovery._recover_one_item", side_effect=lambda *args, **kwargs: next(results)):
        state = run_deleted_paper_recovery(kb, report, max_items=1)
        assert len(state["pending"]) == 1
        state = run_deleted_paper_recovery(kb, report, max_items=1)

    assert len(state["pending"]) == 0
    assert len(state["restored"]) == 1
    assert len(state["skipped"]) == 1


def test_recovery_failed_item_does_not_block_queue(tmp_path: Path) -> None:
    """One failed recovery item should not prevent later pending items from running."""
    kb = tmp_path / "kb"
    (kb / ".papermind" / "recovery").mkdir(parents=True)
    report = kb / ".papermind" / "reports" / "report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "findings": [
                    {"title": "Paper Fail", "path": "papers/hydrology/paper-fail/paper.md", "paper_id": "paper-fail"},
                    {"title": "Paper Pass", "path": "papers/hydrology/paper-pass/paper.md", "paper_id": "paper-pass"},
                ]
            }
        )
    )

    results = iter(
        [
            {"bucket": "failed", "record": {"title": "Paper Fail", "topic": "hydrology", "reason": "download_failed"}},
            {"bucket": "restored", "record": {"title": "Paper Pass", "topic": "hydrology", "reason": "restored"}},
        ]
    )

    with patch("papermind.recovery._recover_one_item", side_effect=lambda *args, **kwargs: next(results)):
        state = run_deleted_paper_recovery(kb, report)

    assert len(state["pending"]) == 0
    assert len(state["failed"]) == 1
    assert len(state["restored"]) == 1
