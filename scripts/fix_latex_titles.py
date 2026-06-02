"""Repair LaTeX/BibTeX/HTML-encoded titles and abstracts in a PaperMind KB.

Decodes LaTeX escapes (BibTeX brace-protection ``{{...}}``, accents ``\\"o``,
Cyrillic ``\\cyrchar...``, dashes) and strips publisher HTML — both plain
(``Q<sub>flow</sub>``) and LaTeX-escaped (``$<$}p{$>``) — to clean Unicode in
each ``paper.md``:

1. the frontmatter ``title:`` field (LaTeX decode), and
2. the leading ``# {title}`` H1 shim in the body (what ``qmd`` returns as the
   search-result title), and
3. the frontmatter ``abstract:`` field (LaTeX decode **and** HTML strip — the
   abstract is the primary searchable text for much of the corpus).

Only ``paper.md`` is processed: the raw sibling is archived as
``original.markdown`` (un-indexed by qmd's ``**/*.md`` pattern; see
``scripts/unindex_original_md.py``), so it is not searched and needs no cleaning.

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
from papermind.ingestion.latex_titles import (
    clean_body_heading,
    clean_scientific_text,
    decode_latex_title,
    looks_html_junk,
)

# One repair record: (path, loaded post, new_title|None, new_abstract|None, new_body).
Target = tuple[Path, frontmatter.Post, str | None, str | None, str]


def _residual_markers(text: str) -> str:
    """Short label of encoding markers still present after cleaning (audit)."""
    found = []
    if "\\" in text:
        found.append("backslash")
    if looks_html_junk(text):
        found.append("html-junk")
    return ",".join(found)


def _find_targets(kb: Path) -> list[Target]:
    """Return repair records for paper.md files needing title/abstract repair."""
    targets: list[Target] = []
    for md in sorted((kb / "papers").rglob("paper.md")):
        try:
            post = frontmatter.load(md)
        except Exception:
            continue

        old_title = str(post.metadata.get("title", "") or "")
        new_title = decode_latex_title(old_title)
        title_changed = (
            bool(new_title) and new_title != old_title and "\\" not in new_title
        )

        old_abstract = str(post.metadata.get("abstract", "") or "")
        cleaned_abstract = clean_scientific_text(old_abstract)
        abstract_changed = bool(cleaned_abstract) and cleaned_abstract != old_abstract

        new_content, body_changed = clean_body_heading(post.content)

        if title_changed or abstract_changed or body_changed:
            targets.append(
                (
                    md,
                    post,
                    new_title if title_changed else None,
                    cleaned_abstract if abstract_changed else None,
                    new_content,
                )
            )
    return targets


def _print_dry_run(targets: list[Target]) -> None:
    """Summarise the planned repair, with a residual-marker audit + samples."""
    n_title = sum(1 for _, _, t, _, _ in targets if t is not None)
    n_abstract = sum(1 for _, _, _, a, _ in targets if a is not None)
    print(
        f"{len(targets)} paper(s) to repair "
        f"({n_title} titles + {n_abstract} abstracts + body H1s)\n"
    )

    # Residual audit: cleaned abstracts that still carry encoding markers.
    residual = [
        (md.parent.name, _residual_markers(a))
        for md, _, _, a, _ in targets
        if a is not None and _residual_markers(a)
    ]
    print(f"abstracts with residual markers after cleaning: {len(residual)}")
    for name, markers in residual[:8]:
        print(f"  ! {name[:56]}  [{markers}]")

    # Before/after samples (post.metadata still holds the OLD values pre-apply).
    print("\nsample abstract repairs:")
    shown = 0
    for md, post, _, new_abstract, _ in targets:
        if new_abstract is None:
            continue
        old = str(post.metadata.get("abstract", "") or "")
        print(f"  [{md.parent.name[:50]}]")
        print(f"    - {old[:90]}")
        print(f"    + {new_abstract[:90]}")
        shown += 1
        if shown >= 4:
            break

    print("\nDry-run only. Re-run with --apply to write.")


def main() -> None:
    """Run the title/abstract repair (dry-run unless ``--apply``)."""
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

    if not args.apply:
        _print_dry_run(targets)
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

    # 2. Rewrite frontmatter title + abstract + body H1 (order preserved, Unicode raw)
    for md, post, new_title, new_abstract, new_content in targets:
        dest = backup / md.relative_to(kb)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(md, dest)
        if new_title is not None:
            post["title"] = new_title
        if new_abstract is not None:
            post["abstract"] = new_abstract
        post.content = new_content
        md.write_text(
            frontmatter.dumps(post, sort_keys=False, allow_unicode=True) + "\n"
        )
    print(f"Repaired {len(targets)} files. Backups: {backup}")

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
