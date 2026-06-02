"""Repair LaTeX/BibTeX-encoded paper titles in a PaperMind KB to Unicode.

Decodes LaTeX escapes (BibTeX brace-protection ``{{...}}``, accents ``\\"o``,
Cyrillic ``\\cyrchar...``, LaTeX dashes) to clean Unicode in BOTH places a
title lives in each ``paper.md``:

1. the frontmatter ``title:`` field (what the catalog/JSON store), and
2. the leading ``# {title}`` H1 shim in the body (what ``qmd`` returns as the
   search-result title).

It then rebuilds the catalog (SQLite ``papermind.db`` + ``catalog.json`` +
``catalog.md``) from the now-authoritative frontmatter. Touched files are
backed up first. Idempotent: a second run finds nothing to fix.

Usage::

    python scripts/fix_latex_titles.py --kb ~/Documents/KnowledgeBase          # dry-run
    python scripts/fix_latex_titles.py --kb ~/Documents/KnowledgeBase --apply  # write
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import frontmatter

from papermind.catalog.index import CatalogIndex
from papermind.catalog.render import render_catalog_md
from papermind.ingestion.latex_titles import decode_latex_title, looks_latex_encoded


def _decode_body_heading(content: str) -> tuple[str, bool]:
    """Decode the leading ``# ...`` H1 heading if it is LaTeX-encoded.

    Returns ``(new_content, changed)``. Only the first non-blank line is
    considered, and only when it is an H1.
    """
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if line.startswith("# "):
            heading = line[2:].strip()
            if looks_latex_encoded(heading):
                decoded = decode_latex_title(heading)
                if decoded and "\\" not in decoded:
                    lines[i] = "# " + decoded
                    return "\n".join(lines), True
        return content, False  # first real line handled (or not an H1)
    return content, False


def _find_targets(kb: Path) -> list[tuple[Path, frontmatter.Post, str | None, str]]:
    """Return (path, post, new_title_or_None, new_content) for files needing repair."""
    targets: list[tuple[Path, frontmatter.Post, str | None, str]] = []
    # Process both the canonical paper.md and the raw original.md sibling: qmd
    # indexes every *.md, so an undecoded original.md surfaces as a duplicate,
    # encoded search hit. original.md carries no `type:` so the catalog rebuild
    # ignores it.
    for md in sorted((kb / "papers").rglob("*.md")):
        try:
            post = frontmatter.load(md)
        except Exception:
            continue
        old_title = str(post.metadata.get("title", "") or "")
        new_title = decode_latex_title(old_title)
        title_changed = new_title and new_title != old_title and "\\" not in new_title
        new_content, body_changed = _decode_body_heading(post.content)
        if title_changed or body_changed:
            targets.append(
                (md, post, new_title if title_changed else None, new_content)
            )
    return targets


def main() -> None:
    """Run the title repair (dry-run unless ``--apply``)."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--kb",
        default=str(Path.home() / "Documents" / "KnowledgeBase"),
        help="Knowledge base root.",
    )
    ap.add_argument(
        "--apply", action="store_true", help="Write changes (default: dry-run)."
    )
    args = ap.parse_args()
    kb = Path(args.kb).expanduser()

    targets = _find_targets(kb)
    n_title = sum(1 for _, _, t, _ in targets if t is not None)
    print(
        f"{len(targets)} file(s) to repair ({n_title} frontmatter titles + body H1s)\n"
    )
    for md, _, t, _ in targets[:8]:
        print(f"  - {md.parent.name[:64]}  (title={'yes' if t else 'H1-only'})")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to write.")
        return

    if not targets:
        print("Nothing to do.")
        return

    # 1. Back up catalog + db + each touched paper.md
    backup = kb / ".papermind" / "backups" / "latex_titles_fix"
    backup.mkdir(parents=True, exist_ok=True)
    if (kb / "catalog.json").exists():
        shutil.copy2(kb / "catalog.json", backup / "catalog.json")
    db = kb / ".papermind" / "papermind.db"
    if db.exists():
        shutil.copy2(db, backup / "papermind.db")

    # 2. Rewrite frontmatter titles + body H1 (order preserved, Unicode raw)
    for md, post, new_title, new_content in targets:
        dest = backup / md.relative_to(kb)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(md, dest)
        if new_title is not None:
            post["title"] = new_title
        post.content = new_content
        md.write_text(
            frontmatter.dumps(post, sort_keys=False, allow_unicode=True) + "\n"
        )
    print(f"\nRepaired {len(targets)} files. Backups: {backup}")

    # 3. Rebuild derived caches from frontmatter, with a guard
    before = len(CatalogIndex(kb).entries)
    idx = CatalogIndex.rebuild(kb)
    after = len(idx.entries)
    if after != before:
        raise SystemExit(
            f"ABORT: entry count changed {before} -> {after}; restore from {backup}"
        )

    # 4. Regenerate the human-readable catalog.md
    (kb / "catalog.md").write_text(render_catalog_md(idx.entries))

    print(f"Rebuilt catalog ({after} entries) + catalog.md.")
    print("Next: re-embed search index with `qmd update && qmd embed`.")


if __name__ == "__main__":
    main()
