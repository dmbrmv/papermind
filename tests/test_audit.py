"""Tests for papermind audit commands."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import frontmatter
from typer.testing import CliRunner

from papermind.cli.main import app

runner = CliRunner()


def _make_kb_with_verified(tmp_path: Path) -> Path:
    """Create a KB with papers in various verification states."""
    kb = tmp_path / "kb"
    runner.invoke(app, ["init", str(kb)])

    papers_dir = kb / "papers" / "hydrology"
    papers_dir.mkdir(parents=True)

    # Paper 1: never verified
    d1 = papers_dir / "paper-a"
    d1.mkdir()
    post1 = frontmatter.Post("# Paper A")
    post1.metadata = {
        "type": "paper",
        "id": "paper-a",
        "title": "Paper A",
        "topic": "hydrology",
    }
    (d1 / "paper.md").write_text(frontmatter.dumps(post1))

    # Paper 2: verified recently
    d2 = papers_dir / "paper-b"
    d2.mkdir()
    post2 = frontmatter.Post("# Paper B")
    post2.metadata = {
        "type": "paper",
        "id": "paper-b",
        "title": "Paper B",
        "topic": "hydrology",
        "last_verified": date.today().isoformat(),
    }
    (d2 / "paper.md").write_text(frontmatter.dumps(post2))

    # Paper 3: verified long ago
    d3 = papers_dir / "paper-c"
    d3.mkdir()
    post3 = frontmatter.Post("# Paper C")
    old_date = (date.today() - timedelta(days=200)).isoformat()
    post3.metadata = {
        "type": "paper",
        "id": "paper-c",
        "title": "Paper C",
        "topic": "hydrology",
        "last_verified": old_date,
    }
    (d3 / "paper.md").write_text(frontmatter.dumps(post3))

    catalog = [
        {
            "id": f"paper-{x}",
            "type": "paper",
            "title": f"Paper {x.upper()}",
            "path": f"papers/hydrology/paper-{x}/paper.md",
            "topic": "hydrology",
        }
        for x in ["a", "b", "c"]
    ]
    (kb / "catalog.json").write_text(json.dumps(catalog))
    return kb


def test_audit_stale_finds_unverified(tmp_path: Path) -> None:
    """audit stale should flag papers without last_verified."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "stale", "--days", "90"])
    assert result.exit_code == 0
    assert "never verified" in result.output
    assert "paper-a" in result.output


def test_audit_stale_finds_old_verified(tmp_path: Path) -> None:
    """audit stale should flag papers verified >90 days ago."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "stale", "--days", "90"])
    assert "paper-c" in result.output


def test_audit_stale_excludes_recent(tmp_path: Path) -> None:
    """Recently verified papers should not be flagged."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "stale", "--days", "90"])
    assert "paper-b" not in result.output


def test_audit_verify_marks_paper(tmp_path: Path) -> None:
    """audit verify should set last_verified to today."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "verify", "paper-a"])
    assert result.exit_code == 0
    assert "Verified" in result.output

    # Check frontmatter was updated
    post = frontmatter.load(kb / "papers" / "hydrology" / "paper-a" / "paper.md")
    assert post.metadata["last_verified"] == date.today().isoformat()


def test_audit_verify_with_note(tmp_path: Path) -> None:
    """audit verify --note should store the note."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(
        app,
        [
            "--kb",
            str(kb),
            "audit",
            "verify",
            "paper-a",
            "--note",
            "Checked OK",
        ],
    )
    assert result.exit_code == 0

    post = frontmatter.load(kb / "papers" / "hydrology" / "paper-a" / "paper.md")
    assert post.metadata["verification_note"] == "Checked OK"


def test_audit_verify_not_found(tmp_path: Path) -> None:
    """audit verify for unknown paper should fail."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "verify", "nonexistent"])
    assert result.exit_code == 1


def test_audit_integrity_detects_duplicate_doi(tmp_path: Path) -> None:
    """audit integrity should flag duplicate DOIs in the catalog."""
    kb = _make_kb_with_verified(tmp_path)
    papers_dir = kb / "papers" / "hydrology"

    post4 = frontmatter.Post("# Paper D")
    post4.metadata = {
        "type": "paper",
        "id": "paper-d",
        "title": "Paper D",
        "topic": "hydrology",
        "doi": "10.1/dup",
    }
    d4 = papers_dir / "paper-d"
    d4.mkdir()
    (d4 / "paper.md").write_text(frontmatter.dumps(post4))

    post5 = frontmatter.Post("# Paper E")
    post5.metadata = {
        "type": "paper",
        "id": "paper-e",
        "title": "Paper E",
        "topic": "hydrology",
        "doi": "10.1/dup",
    }
    d5 = papers_dir / "paper-e"
    d5.mkdir()
    (d5 / "paper.md").write_text(frontmatter.dumps(post5))

    catalog = json.loads((kb / "catalog.json").read_text())
    catalog.extend(
        [
            {
                "id": "paper-d",
                "type": "paper",
                "title": "Paper D",
                "path": "papers/hydrology/paper-d/paper.md",
                "topic": "hydrology",
                "doi": "10.1/dup",
            },
            {
                "id": "paper-e",
                "type": "paper",
                "title": "Paper E",
                "path": "papers/hydrology/paper-e/paper.md",
                "topic": "hydrology",
                "doi": "10.1/dup",
            },
        ]
    )
    (kb / "catalog.json").write_text(json.dumps(catalog))

    result = runner.invoke(app, ["--kb", str(kb), "audit", "integrity"])
    assert result.exit_code == 1
    assert "duplicate_doi" in result.output


def test_audit_integrity_json_output(tmp_path: Path) -> None:
    """audit integrity --json should emit a JSON report."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "integrity", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "summary" in payload
    assert "findings" in payload


def test_audit_integrity_online_mismatch_warning(tmp_path: Path) -> None:
    """Online integrity mode should flag DOI/title mismatches."""
    kb = _make_kb_with_verified(tmp_path)
    paper = kb / "papers" / "hydrology" / "paper-a" / "paper.md"
    post = frontmatter.load(paper)
    post.metadata["doi"] = "10.1234/mismatch"
    post.metadata["title"] = "Local Hydrology Title"
    paper.write_text(frontmatter.dumps(post))

    catalog = json.loads((kb / "catalog.json").read_text())
    catalog[0]["doi"] = "10.1234/mismatch"
    (kb / "catalog.json").write_text(json.dumps(catalog))

    with patch(
        "papermind.integrity._fetch_openalex_title",
        return_value="Completely Different Remote Title",
    ):
        result = runner.invoke(
            app,
            ["--kb", str(kb), "audit", "integrity", "--online", "--fail-on", "never"],
        )

    assert result.exit_code == 0
    assert "doi_title_mismatch" in result.output


def test_audit_health_reports_freshness_and_integrity(tmp_path: Path) -> None:
    """audit health should print both freshness and integrity summaries."""
    kb = _make_kb_with_verified(tmp_path)
    result = runner.invoke(app, ["--kb", str(kb), "audit", "health", "--fail-on", "never"])
    assert result.exit_code == 0
    assert "Freshness:" in result.output
    assert "Integrity:" in result.output


def test_audit_intake_passes_for_indexed_matching_paper(tmp_path: Path) -> None:
    """audit intake should pass for a valid ingested paper."""
    kb = _make_kb_with_verified(tmp_path)
    paper = kb / "papers" / "hydrology" / "paper-a" / "paper.md"
    post = frontmatter.load(paper)
    post.metadata["doi"] = "10.1234/right"
    post.metadata["title"] = "Hydrology Title"
    post.metadata["year"] = 2021
    paper.write_text(frontmatter.dumps(post))

    catalog = json.loads((kb / "catalog.json").read_text())
    catalog[0]["doi"] = "10.1234/right"
    catalog[0]["title"] = "Hydrology Title"
    (kb / "catalog.json").write_text(json.dumps(catalog))

    with patch(
        "papermind.integrity._fetch_openalex_title",
        return_value="Hydrology Title",
    ):
        result = runner.invoke(app, ["--kb", str(kb), "audit", "intake", "paper-a"])

    assert result.exit_code == 0
    assert "Paper intake passed" in result.output


def test_audit_intake_fails_for_online_mismatch(tmp_path: Path) -> None:
    """audit intake should fail when DOI/title verification mismatches."""
    kb = _make_kb_with_verified(tmp_path)
    paper = kb / "papers" / "hydrology" / "paper-a" / "paper.md"
    post = frontmatter.load(paper)
    post.metadata["doi"] = "10.1234/wrong"
    post.metadata["title"] = "Local Title"
    post.metadata["year"] = 2021
    paper.write_text(frontmatter.dumps(post))

    catalog = json.loads((kb / "catalog.json").read_text())
    catalog[0]["doi"] = "10.1234/wrong"
    catalog[0]["title"] = "Local Title"
    (kb / "catalog.json").write_text(json.dumps(catalog))

    with patch(
        "papermind.integrity._fetch_openalex_title",
        return_value="Different Remote Title",
    ):
        result = runner.invoke(app, ["--kb", str(kb), "audit", "intake", "paper-a"])

    assert result.exit_code == 1
    assert "doi_title_mismatch" in result.output


def test_audit_repair_plan_proposes_year_from_doi(tmp_path: Path) -> None:
    """repair-plan should propose a year when DOI metadata matches the title."""
    kb = _make_kb_with_verified(tmp_path)
    paper = kb / "papers" / "hydrology" / "paper-a" / "paper.md"
    post = frontmatter.load(paper)
    post.metadata["doi"] = "10.1234/right"
    post.metadata["title"] = "Hydrology Title"
    paper.write_text(frontmatter.dumps(post))

    catalog = json.loads((kb / "catalog.json").read_text())
    catalog[0]["doi"] = "10.1234/right"
    (kb / "catalog.json").write_text(json.dumps(catalog))

    with patch(
        "papermind.repair._fetch_openalex_work_by_doi",
        return_value={"title": "Hydrology Title", "year": 2021, "doi": "10.1234/right"},
    ):
        result = runner.invoke(app, ["--kb", str(kb), "audit", "repair-plan", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["summary"]["high"] == 1
    assert payload["actions"][0]["code"] == "set_year_from_doi"
    assert payload["actions"][0]["proposed_value"] == "2021"


def test_audit_repair_plan_proposes_doi_replacement_from_title_match(tmp_path: Path) -> None:
    """repair-plan should propose DOI replacement when title search is strong."""
    kb = _make_kb_with_verified(tmp_path)
    paper = kb / "papers" / "hydrology" / "paper-a" / "paper.md"
    post = frontmatter.load(paper)
    post.metadata["doi"] = "10.1234/wrong"
    post.metadata["title"] = "Operational SWAT Model Advancing Seasonal Forecasting"
    paper.write_text(frontmatter.dumps(post))

    catalog = json.loads((kb / "catalog.json").read_text())
    catalog[0]["doi"] = "10.1234/wrong"
    catalog[0]["title"] = "Operational SWAT Model Advancing Seasonal Forecasting"
    (kb / "catalog.json").write_text(json.dumps(catalog))

    with (
        patch(
            "papermind.repair._fetch_openalex_work_by_doi",
            return_value={
                "title": "A Completely Different Paper",
                "year": 1998,
                "doi": "10.1234/wrong",
            },
        ),
        patch(
            "papermind.repair._search_openalex_by_title",
            return_value=[
                {
                    "title": "Operational SWAT Model Advancing Seasonal Forecasting",
                    "year": 2024,
                    "doi": "10.5678/correct",
                }
            ],
        ),
    ):
        result = runner.invoke(app, ["--kb", str(kb), "audit", "repair-plan", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    codes = {action["code"] for action in payload["actions"]}
    assert "replace_doi_from_title_match" in codes


def test_audit_repair_apply_updates_frontmatter_and_catalog(tmp_path: Path) -> None:
    """repair-apply should write selected high-confidence repairs."""
    kb = _make_kb_with_verified(tmp_path)
    paper = kb / "papers" / "hydrology" / "paper-a" / "paper.md"
    post = frontmatter.load(paper)
    post.metadata["title"] = "Hydrology Title"
    paper.write_text(frontmatter.dumps(post))

    with (
        patch(
            "papermind.repair._fetch_openalex_work_by_doi",
            return_value={"title": "", "year": None, "doi": ""},
        ),
        patch(
            "papermind.repair._search_openalex_by_title",
            return_value=[
                {"title": "Hydrology Title", "year": 2020, "doi": "10.9999/hydro"}
            ],
        ),
    ):
        result = runner.invoke(
            app,
            ["--kb", str(kb), "audit", "repair-apply", "--min-confidence", "high"],
        )

    assert result.exit_code == 0
    updated = frontmatter.load(paper)
    assert updated.metadata["doi"] == "10.9999/hydro"
    assert updated.metadata["year"] == 2020

    catalog = json.loads((kb / "catalog.json").read_text())
    paper_entry = next(entry for entry in catalog if entry["id"] == "paper-a")
    assert paper_entry["doi"] == "10.9999/hydro"


def test_audit_recover_deleted_reports_state_summary(tmp_path: Path) -> None:
    """recover-deleted should print a summary after processing."""
    kb = _make_kb_with_verified(tmp_path)
    report = kb / ".papermind" / "reports" / "integrity_online_post_repair_2026-03-26.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"findings": []}))

    fake_state = {
        "source_report": str(report),
        "pending": [{"title": "Paper X"}],
        "restored": [{"title": "Paper A"}],
        "skipped": [{"title": "Paper B"}],
        "failed": [],
    }

    with patch("papermind.recovery.run_deleted_paper_recovery", return_value=fake_state):
        result = runner.invoke(app, ["--kb", str(kb), "audit", "recover-deleted"])

    assert result.exit_code == 0
    assert "restored=1" in result.output
    assert "pending=1" in result.output


def test_audit_recover_status_prints_next_pending(tmp_path: Path) -> None:
    """recover-status should show queue summary and next pending item."""
    kb = _make_kb_with_verified(tmp_path)
    state_file = kb / ".papermind" / "recovery" / "deleted_papers_recovery.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "source_report": "report.json",
                "last_run_started_at": "2026-03-26T11:00:00+00:00",
                "last_run_finished_at": "2026-03-26T11:10:00+00:00",
                "pending": [{"title": "Paper Next"}],
                "restored": [{"title": "Paper Done"}],
                "skipped": [],
                "failed": [],
            }
        )
    )

    result = runner.invoke(app, ["--kb", str(kb), "audit", "recover-status"])
    assert result.exit_code == 0
    assert "Last run started:" in result.output
    assert "Last run finished:" in result.output
    assert "Next pending: Paper Next" in result.output


def test_audit_recover_retry_requeues_failed_items(tmp_path: Path) -> None:
    """recover-retry should move failed recovery items back into pending."""
    kb = _make_kb_with_verified(tmp_path)
    state_file = kb / ".papermind" / "recovery" / "deleted_papers_recovery.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "source_report": "report.json",
                "pending": [],
                "restored": [],
                "skipped": [],
                "failed": [
                    {
                        "title": "Paper Retry",
                        "topic": "hydrology",
                        "requested_path": "papers/hydrology/paper-retry/paper.md",
                        "requested_paper_id": "paper-retry",
                        "reason": "download_failed",
                    }
                ],
            }
        )
    )

    result = runner.invoke(app, ["--kb", str(kb), "audit", "recover-retry", "--retry", "failed"])
    assert result.exit_code == 0
    assert "pending=1" in result.output

    state = json.loads(state_file.read_text())
    assert state["failed"] == []
    assert state["pending"][0]["title"] == "Paper Retry"


def test_audit_recover_retry_rejects_unknown_class(tmp_path: Path) -> None:
    """recover-retry should fail on unknown retry classes."""
    kb = _make_kb_with_verified(tmp_path)
    state_file = kb / ".papermind" / "recovery" / "deleted_papers_recovery.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "source_report": "report.json",
                "pending": [],
                "restored": [],
                "skipped": [],
                "failed": [],
            }
        )
    )

    result = runner.invoke(
        app,
        ["--kb", str(kb), "audit", "recover-retry", "--retry", "made_up_reason"],
    )
    assert result.exit_code == 1
    assert "Unknown retry class" in result.output
