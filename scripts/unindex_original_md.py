"""Un-index raw ``original.md`` archival copies from a PaperMind KB.

``qmd`` indexes every ``**/*.md`` under the collection root with no file-level
exclude, so each paper's raw ``original.md`` sibling is indexed alongside the
canonical, cleaned ``paper.md`` — doubling search results and surfacing the raw
PDF-conversion HTML/LaTeX that ``paper.md`` has already had cleaned. The
``qmd_search`` wrapper de-dups this for the programmatic path, but the raw
``qmd query`` CLI (the human workflow) bypasses the wrapper and still sees both.

This renames each ``papers/**/original.md`` to ``original.markdown``: still a
readable Markdown source on disk, but it no longer matches ``**/*.md`` so ``qmd``
stops indexing it. ``paper.md`` remains the single indexed, canonical copy. The
rename is loss-free (the raw source is preserved, just un-indexed) and recorded
to a manifest so it can be reverted.

After applying, re-index with ``qmd update`` (drops the now-absent ``.md``
files from the index). New intake writes ``original.markdown`` directly
(``ingestion/paper.py``), so this is a one-time migration for existing papers.

Usage (``--kb`` defaults to ``~/Documents/KnowledgeBase``)::

    python scripts/unindex_original_md.py            # dry-run (default)
    python scripts/unindex_original_md.py --apply    # rename original.md
    python scripts/unindex_original_md.py --revert    # undo via manifest
"""

from __future__ import annotations

import argparse
from pathlib import Path

_OLD_NAME = "original.md"
_NEW_NAME = "original.markdown"
_MANIFEST_REL = Path(".papermind") / "backups" / "unindex_original_md" / "manifest.tsv"


def _find_old(kb: Path) -> list[Path]:
    """Return every ``papers/**/original.md`` under the KB."""
    papers = kb / "papers"
    if not papers.exists():
        return []
    return sorted(p for p in papers.rglob(_OLD_NAME) if p.is_file())


def _apply(kb: Path) -> None:
    """Rename ``original.md`` -> ``original.markdown`` and write a manifest."""
    targets = _find_old(kb)
    if not targets:
        print("Nothing to do — no original.md files found.")
        return

    manifest = kb / _MANIFEST_REL
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    renamed = 0
    for old in targets:
        new = old.with_name(_NEW_NAME)
        if new.exists():
            print(f"  skip (target exists): {old.relative_to(kb)}")
            continue
        old.rename(new)
        lines.append(f"{old.relative_to(kb)}\t{new.relative_to(kb)}")
        renamed += 1
    manifest.write_text("\n".join(lines) + ("\n" if lines else ""))
    print(f"Renamed {renamed} file(s). Manifest: {manifest}")
    print("Next: `qmd update` to drop the now-absent .md files from the index.")


def _revert(kb: Path) -> None:
    """Rename ``original.markdown`` back to ``original.md`` via the manifest."""
    manifest = kb / _MANIFEST_REL
    if not manifest.exists():
        print(f"No manifest at {manifest}; nothing to revert.")
        return
    restored = 0
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        old_rel, new_rel = line.split("\t")
        new = kb / new_rel
        old = kb / old_rel
        if new.exists() and not old.exists():
            new.rename(old)
            restored += 1
    print(f"Restored {restored} file(s) to original.md. Run `qmd update` to re-index.")


def main() -> None:
    """Run the un-index migration (dry-run unless ``--apply``/``--revert``)."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--kb",
        default=str(Path.home() / "Documents" / "KnowledgeBase"),
        help="Knowledge base root.",
    )
    ap.add_argument(
        "--apply", action="store_true", help="Rename original.md -> original.markdown."
    )
    ap.add_argument("--revert", action="store_true", help="Undo via the manifest.")
    args = ap.parse_args()
    kb = Path(args.kb).expanduser()

    if args.revert:
        _revert(kb)
        return
    if args.apply:
        _apply(kb)
        return

    targets = _find_old(kb)
    print(f"{len(targets)} original.md file(s) would be renamed to original.markdown.")
    for p in targets[:5]:
        print(f"  {p.relative_to(kb)}  ->  {p.with_name(_NEW_NAME).relative_to(kb)}")
    if len(targets) > 5:
        print(f"  ... and {len(targets) - 5} more")
    print("\nDry-run only. Re-run with --apply to rename, --revert to undo.")


if __name__ == "__main__":
    main()
