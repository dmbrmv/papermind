# Recovery Backlog

Ordered follow-up work for PaperMind deleted-paper recovery and intake hardening.
This file is the durable task list to preserve sequencing across compaction and handoffs.

## Current Goal

Make deleted-paper recovery operationally reliable, observable, and resumable enough
to run as a background workflow against a live KB without losing trust.

## Ordered Tasks

1. `completed` Improve recovery observability
   - Add per-paper log lines with timestamps.
   - Persist lifecycle details in the recovery state file.
   - Record discovery match, download result, OCR start/end, ingest result, and intake result.

2. `completed` Add retry classes and selective retry support
   - Classify failures into concrete buckets such as `download_failed`, `ocr_failed`,
     `ocr_timeout`, `title_mismatch`, `intake_failed`, and `no_candidate`.
   - Support retrying only selected failure classes.

3. `completed` Bound OCR runtime
   - Add limits for max pages, OCR timeout, and oversized PDFs.
   - Add an explicit fast mode for recovery-oriented OCR runs.

4. `completed` Add quarantine output for unresolved papers
   - Keep structured context for papers that are not safe to restore.
   - Preserve candidate title, DOI, similarity, PDF URL, and failure reason.

5. `completed` Persist per-paper intake artifacts
   - Write intake verification reports for restored papers under `.papermind/recovery/intake/`.

6. `completed` Auto-verify freshness for restored papers
   - Set or update `last_verified` for successfully restored papers.

7. `completed` Extend `doctor` for recovery health
   - Show OCR availability, recovery state existence, pending/failed counts, and active runner hints.

8. `completed` Add a managed background runner wrapper
   - Provide a stable launch script with pid/log handling and safe restart behavior.

9. `completed` Add deeper recovery integration tests
   - Cover resume-after-interruption, failed-item isolation, duplicate DOI skip, and intake failure routing.

10. `completed` Resolve remaining non-fatal metadata gaps
    - Backfill remaining `missing_year` cases automatically when confidence is high.

## Notes

- Deleted-paper recovery is currently driven by:
  - `papermind audit recover-deleted`
  - `papermind audit recover-status`
- Live KB state is tracked in:
  - `.papermind/recovery/deleted_papers_recovery.json`
  - `.papermind/recovery/deleted_papers_recovery.log`
