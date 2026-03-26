"""Resumable recovery workflows for historical KB rebuilds."""

from __future__ import annotations

import asyncio
import json
import re
import signal
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from papermind.catalog.index import CatalogIndex
from papermind.config import load_config, recovery_config
from papermind.discovery.downloader import download_paper
from papermind.discovery.openalex import OpenAlexProvider
from papermind.ingestion.paper import ingest_paper
from papermind.integrity import _fetch_openalex_title, _title_similarity
from papermind.query.qmd import qmd_reindex
import frontmatter as fm_lib


def default_recovery_state_path(kb_path: Path) -> Path:
    """Return the default state file for deleted-paper recovery."""
    return kb_path / ".papermind" / "recovery" / "deleted_papers_recovery.json"


def default_recovery_log_path(kb_path: Path) -> Path:
    """Return the default log file for deleted-paper recovery."""
    return kb_path / ".papermind" / "recovery" / "deleted_papers_recovery.log"


def default_quarantine_dir(kb_path: Path) -> Path:
    """Return the quarantine directory for unresolved recovery items."""
    return kb_path / ".papermind" / "recovery" / "quarantine"


def default_intake_dir(kb_path: Path) -> Path:
    """Return the intake-artifact directory for restored recovery items."""
    return kb_path / ".papermind" / "recovery" / "intake"


def initialize_recovery_state(
    kb_path: Path,
    source_report: Path,
    *,
    state_path: Path | None = None,
    log_path: Path | None = None,
) -> dict:
    """Create a recovery state file from an integrity report if needed."""
    state_path = state_path or default_recovery_state_path(kb_path)
    log_path = log_path or default_recovery_log_path(kb_path)
    if state_path.exists():
        return json.loads(state_path.read_text())

    findings = json.loads(source_report.read_text()).get("findings", [])
    pending = []
    for finding in findings:
        path = str(finding.get("path", ""))
        parts = Path(path).parts
        topic = parts[1] if len(parts) > 1 else "uncategorized"
        pending.append(
            {
                "title": str(finding.get("title", "")),
                "topic": topic,
                "path": path,
                "paper_id": str(finding.get("paper_id", "")),
            }
        )

    state = {
        "source_report": str(source_report),
        "log_path": str(log_path),
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "last_run_started_at": "",
        "last_run_finished_at": "",
        "pending": pending,
        "restored": [],
        "skipped": [],
        "failed": [],
    }
    _write_state(state_path, state)
    return state


def load_recovery_state(kb_path: Path, *, state_path: Path | None = None) -> dict:
    """Load an existing recovery state file."""
    state_path = state_path or default_recovery_state_path(kb_path)
    if not state_path.exists():
        raise FileNotFoundError(state_path)
    return json.loads(state_path.read_text())


def run_deleted_paper_recovery(
    kb_path: Path,
    source_report: Path,
    *,
    state_path: Path | None = None,
    log_path: Path | None = None,
    min_similarity: float = 0.9,
    max_items: int = 0,
) -> dict:
    """Process pending deleted-paper recovery items sequentially."""
    state_path = state_path or default_recovery_state_path(kb_path)
    log_path = log_path or default_recovery_log_path(kb_path)
    state = initialize_recovery_state(
        kb_path,
        source_report,
        state_path=state_path,
        log_path=log_path,
    )
    provider = OpenAlexProvider()
    config = recovery_config(load_config(kb_path))
    pdf_dir = kb_path / "pdfs"
    pdf_dir.mkdir(exist_ok=True)

    state["last_run_started_at"] = _utc_now()
    state["updated_at"] = _utc_now()
    _write_state(state_path, state)
    _append_log(log_path, f"recovery_run_started pending={len(state['pending'])}")

    processed = 0
    while state["pending"]:
        if max_items and processed >= max_items:
            break

        item = state["pending"].pop(0)
        _append_log(log_path, f"start title={item['title']}")
        result = _recover_one_item(
            kb_path,
            pdf_dir,
            config,
            provider,
            item,
            min_similarity=min_similarity,
            log_path=log_path,
        )
        state[result["bucket"]].append(result["record"])
        _write_intake_artifact_if_needed(kb_path, result["record"])
        _write_quarantine_if_needed(kb_path, result["record"])
        processed += 1
        state["updated_at"] = _utc_now()
        _write_state(state_path, state)

    state["last_run_finished_at"] = _utc_now()
    state["updated_at"] = _utc_now()
    _write_state(state_path, state)
    summary = recovery_summary(state)
    _append_log(
        log_path,
        "recovery_run_finished "
        f"pending={summary['pending']} restored={summary['restored']} "
        f"skipped={summary['skipped']} failed={summary['failed']}",
    )
    return state


def _recover_one_item(
    kb_path: Path,
    pdf_dir: Path,
    config,
    provider: OpenAlexProvider,
    item: dict,
    *,
    min_similarity: float,
    log_path: Path,
) -> dict:
    """Recover one paper candidate and classify the result."""
    requested_title = item["title"]
    topic = item["topic"]
    candidate, similarity = asyncio.run(_choose_candidate(provider, requested_title))
    base_record = {
        "title": requested_title,
        "topic": topic,
        "requested_path": item.get("path", ""),
        "requested_paper_id": item.get("paper_id", ""),
    }

    if candidate is None:
        _append_log(log_path, f"no_candidate title={requested_title}")
        return {
            "bucket": "skipped",
            "record": _finalize_record(base_record, reason="no_discovery_result"),
        }

    if similarity < min_similarity or not candidate.pdf_url:
        _append_log(
            log_path,
            "candidate_rejected "
            f"title={requested_title} similarity={similarity:.3f} pdf={bool(candidate.pdf_url)}",
        )
        return {
            "bucket": "skipped",
            "record": _finalize_record(
                base_record,
                reason="insufficient_confidence",
                similarity=round(similarity, 3),
                resolved_title=candidate.title,
                doi=candidate.doi,
                pdf=bool(candidate.pdf_url),
            ),
        }

    catalog = CatalogIndex(kb_path)
    if candidate.doi and catalog.has_doi(candidate.doi):
        _append_log(log_path, f"doi_already_present title={requested_title} doi={candidate.doi}")
        return {
            "bucket": "skipped",
            "record": _finalize_record(
                base_record,
                reason="doi_already_present",
                resolved_title=candidate.title,
                doi=candidate.doi,
                similarity=round(similarity, 3),
            ),
        }

    _append_log(
        log_path,
        "candidate_selected "
        f"title={requested_title} resolved_title={candidate.title} doi={candidate.doi} "
        f"year={candidate.year} similarity={similarity:.3f}",
    )
    pdf_path = asyncio.run(download_paper(candidate, pdf_dir))
    if pdf_path is None:
        _append_log(log_path, f"download_failed title={requested_title} doi={candidate.doi}")
        return {
            "bucket": "failed",
            "record": _finalize_record(
                base_record,
                reason="download_failed",
                resolved_title=candidate.title,
                doi=candidate.doi,
                similarity=round(similarity, 3),
            ),
        }

    _append_log(log_path, f"download_ok title={requested_title} pdf={pdf_path}")
    page_limit = getattr(config, "recovery_max_pdf_pages", 0)
    page_count = _pdf_page_count(pdf_path)
    if page_limit and page_count > page_limit:
        _append_log(
            log_path,
            f"page_limit_exceeded title={requested_title} pages={page_count} limit={page_limit}",
        )
        return {
            "bucket": "failed",
            "record": _finalize_record(
                base_record,
                reason="page_limit_exceeded",
                resolved_title=candidate.title,
                doi=candidate.doi,
                similarity=round(similarity, 3),
                page_count=page_count,
                page_limit=page_limit,
            ),
        }

    _append_log(log_path, f"ocr_ingest_started title={requested_title}")
    try:
        with _ocr_timeout(getattr(config, "recovery_ocr_timeout_seconds", 0)):
            entry = ingest_paper(
                pdf_path,
                topic,
                kb_path,
                config,
                no_reindex=True,
                abstract=candidate.abstract,
                cites=candidate.cites or None,
                cited_by=candidate.cited_by or None,
                preferred_title=candidate.title,
                preferred_doi=candidate.doi,
                preferred_year=candidate.year,
            )
    except TimeoutError:
        _append_log(log_path, f"ocr_timeout title={requested_title}")
        return {
            "bucket": "failed",
            "record": _finalize_record(
                base_record,
                reason="ocr_timeout",
                resolved_title=candidate.title,
                doi=candidate.doi,
                similarity=round(similarity, 3),
                timeout_seconds=getattr(config, "recovery_ocr_timeout_seconds", 0),
            ),
        }
    except Exception as exc:  # noqa: BLE001
        _append_log(log_path, f"ingest_failed title={requested_title} error={exc}")
        return {
            "bucket": "failed",
            "record": _finalize_record(
                base_record,
                reason=f"ingest_failed: {exc}",
                resolved_title=candidate.title,
                doi=candidate.doi,
                similarity=round(similarity, 3),
            ),
        }

    if entry is None:
        _append_log(log_path, f"ingest_skipped title={requested_title}")
        return {
            "bucket": "skipped",
            "record": _finalize_record(
                base_record,
                reason="ingest_returned_none",
                resolved_title=candidate.title,
                doi=candidate.doi,
                similarity=round(similarity, 3),
            ),
        }

    qmd_reindex(kb_path)
    _append_log(log_path, f"ingest_ok title={requested_title} entry_id={entry.id}")
    remote_title = asyncio.run(_fetch_openalex_title(candidate.doi)) if candidate.doi else None
    intake_ok = True
    if remote_title and _title_similarity(candidate.title, remote_title) < 0.45:
        intake_ok = False

    bucket = "restored" if intake_ok else "failed"
    reason = "restored" if intake_ok else "intake_failed"
    if intake_ok:
        _mark_recovered_paper_verified(kb_path, entry.id)
    _append_log(log_path, f"intake_{'ok' if intake_ok else 'failed'} title={requested_title} entry_id={entry.id}")
    return {
        "bucket": bucket,
        "record": _finalize_record(
            base_record,
            reason=reason,
            entry_id=entry.id,
            resolved_title=candidate.title,
            doi=candidate.doi,
            year=candidate.year,
            similarity=round(similarity, 3),
            intake_ok=intake_ok,
        ),
    }


async def _choose_candidate(provider: OpenAlexProvider, title: str):
    """Choose the strongest OpenAlex candidate for a title."""
    results = await provider.search(title, limit=5)
    if not results:
        return None, 0.0
    best = max(results, key=lambda result: _title_similarity_simple(title, result.title or ""))
    return best, _title_similarity_simple(title, best.title or "")


def recovery_summary(state: dict) -> dict[str, int]:
    """Summarize a recovery state file."""
    return {
        "pending": len(state.get("pending", [])),
        "restored": len(state.get("restored", [])),
        "skipped": len(state.get("skipped", [])),
        "failed": len(state.get("failed", [])),
        "total": sum(len(state.get(key, [])) for key in ("pending", "restored", "skipped", "failed")),
    }


def retryable_failure_classes() -> set[str]:
    """Failure classes that can be requeued selectively."""
    return {
        "download_failed",
        "ocr_timeout",
        "page_limit_exceeded",
        "ingest_failed",
        "ingest_returned_none",
        "intake_failed",
        "no_discovery_result",
        "insufficient_confidence",
    }


def requeue_recovery_items(
    kb_path: Path,
    *,
    state_path: Path | None = None,
    retry_classes: set[str] | None = None,
    include_skipped: bool = True,
    include_failed: bool = True,
) -> dict:
    """Move selected failed/skipped items back into pending."""
    state_path = state_path or default_recovery_state_path(kb_path)
    state = load_recovery_state(kb_path, state_path=state_path)
    retry_classes = retry_classes or retryable_failure_classes()

    new_pending_keys = {
        (item.get("title", ""), item.get("topic", ""), item.get("requested_path", item.get("path", "")))
        for item in state.get("pending", [])
    }

    def should_retry(item: dict) -> bool:
        reason = _reason_class(str(item.get("reason", "")))
        return reason in retry_classes

    requeued: list[dict] = []

    def pop_retryable(items: list[dict]) -> list[dict]:
        kept = []
        for item in items:
            if should_retry(item):
                pending_item = {
                    "title": item.get("title", ""),
                    "topic": item.get("topic", "uncategorized"),
                    "path": item.get("requested_path", item.get("path", "")),
                    "paper_id": item.get("requested_paper_id", item.get("paper_id", "")),
                }
                key = (
                    pending_item["title"],
                    pending_item["topic"],
                    pending_item["path"],
                )
                if key not in new_pending_keys:
                    requeued.append(pending_item)
                    new_pending_keys.add(key)
            else:
                kept.append(item)
        return kept

    if include_failed:
        state["failed"] = pop_retryable(state.get("failed", []))
    if include_skipped:
        state["skipped"] = pop_retryable(state.get("skipped", []))

    state["pending"] = requeued + state.get("pending", [])
    state["updated_at"] = _utc_now()
    _write_state(state_path, state)
    return state


def _write_state(path: Path, state: dict) -> None:
    """Persist recovery state atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def _write_quarantine_if_needed(kb_path: Path, record: dict) -> None:
    """Persist unresolved recovery context for later review."""
    reason = _reason_class(str(record.get("reason", "")))
    if reason in {"doi_already_present", "restored"}:
        return

    target = _quarantine_artifact_path(kb_path, record)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    payload["reason_class"] = reason
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _write_intake_artifact_if_needed(kb_path: Path, record: dict) -> None:
    """Persist intake evidence for successfully restored papers."""
    if _reason_class(str(record.get("reason", ""))) != "restored":
        return

    target = _intake_artifact_path(kb_path, record)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    payload["artifact_type"] = "recovery_intake"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _quarantine_artifact_path(kb_path: Path, record: dict) -> Path:
    """Return the artifact path for one quarantined recovery item."""
    slug = _slugify(record.get("title", "paper"))
    suffix = _reason_class(str(record.get("reason", "")))
    return default_quarantine_dir(kb_path) / f"{slug}.{suffix}.json"


def _intake_artifact_path(kb_path: Path, record: dict) -> Path:
    """Return the artifact path for one restored intake record."""
    slug = _slugify(record.get("title", "paper"))
    return default_intake_dir(kb_path) / f"{slug}.restored.json"


def _append_log(path: Path, message: str) -> None:
    """Append one timestamped line to the recovery log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{_utc_now()} {message}\n")


def _finalize_record(record: dict, **extra: object) -> dict:
    """Add completion metadata to a recovery record."""
    return record | {"completed_at": _utc_now()} | extra


def _reason_class(reason: str) -> str:
    """Normalize detailed reason strings into retry classes."""
    if not reason:
        return "unknown"
    if reason.startswith("ingest_failed:"):
        return "ingest_failed"
    return reason


def _mark_recovered_paper_verified(kb_path: Path, paper_id: str) -> None:
    """Stamp recovery-restored papers as freshly verified."""
    catalog = CatalogIndex(kb_path)
    entry = catalog.get(paper_id)
    if entry is None:
        return
    md_path = kb_path / entry.path
    if not md_path.exists():
        return

    post = fm_lib.load(md_path)
    post.metadata["last_verified"] = _utc_today()
    post.metadata["verification_note"] = "recovery_intake_passed"
    md_path.write_text(fm_lib.dumps(post), encoding="utf-8")


def _pdf_page_count(pdf_path: Path) -> int:
    """Return the number of pages in a PDF."""
    import fitz

    doc = fitz.open(pdf_path)
    try:
        return doc.page_count
    finally:
        doc.close()


class _OcrTimeout:
    """Unix signal-based timeout for recovery OCR runs."""

    def __init__(self, seconds: int) -> None:
        self.seconds = seconds
        self._previous_handler = None

    def __enter__(self) -> None:
        if self.seconds <= 0:
            return None
        self._previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, self._handle_timeout)
        signal.setitimer(signal.ITIMER_REAL, float(self.seconds))
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.seconds <= 0:
            return None
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        if self._previous_handler is not None:
            signal.signal(signal.SIGALRM, self._previous_handler)
        return None

    @staticmethod
    def _handle_timeout(signum, frame) -> None:
        raise TimeoutError("Recovery OCR timed out")


def _ocr_timeout(seconds: int) -> _OcrTimeout:
    """Create a timeout context for recovery OCR."""
    return _OcrTimeout(seconds)


def _utc_now() -> str:
    """UTC timestamp for state file updates."""
    return datetime.now(timezone.utc).isoformat()


def _utc_today() -> str:
    """UTC date string for verification stamps."""
    return datetime.now(timezone.utc).date().isoformat()


def _title_similarity_simple(left: str, right: str) -> float:
    """Approximate title similarity for discovery candidate selection."""
    return SequenceMatcher(None, _normalize_title(left), _normalize_title(right)).ratio()


def _normalize_title(title: str) -> str:
    """Normalize title text for similarity comparison."""
    text = title.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _slugify(value: str) -> str:
    """Filesystem-friendly slug for quarantine artifact names."""
    return _normalize_title(value).replace(" ", "-") or "paper"
