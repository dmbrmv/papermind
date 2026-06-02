"""Clean residual HTML-tag junk from PaperMind ``paper.md`` bodies.

After the title/abstract sweep (``scripts/fix_latex_titles.py``), the *body* of
many bib-shim papers still carries the raw HTML→LaTeX conversion junk — escaped
HTML tags like ``$<$}p{$>``, ``{$<$}/strong{$>$}``, ``{$<$}br{$>`` and stray
entities (``&thinsp;``, ``&amp;``). ``qmd`` indexes the full body, so this junk
leaks into search snippets even though the frontmatter is clean.

This is a **string-only** cleaner — it deliberately does **not** run
``latex_to_text`` on bodies. Two hard-won reasons:

* ``%`` is a LaTeX comment char; ``latex_to_text`` silently drops everything from
  the first ``%`` to end-of-line, deleting prose/numbers (verified: a glacier
  abstract lost its entire shrinkage-rate + correlation statistics).
* ``strip_html``'s ``<…>`` tag regex eats literal angle-bracket spans in
  full-text OCR bodies, taking embedded numbers with them (verified: one body
  lost 94 numbers).

So the transform is narrow and provably non-destructive:

1. Remove escaped-HTML-tag junk via a regex **anchored on known tag names**
   (``p|strong|br|q|a|img``) — this is what distinguishes junk (``$<$}p{$>``)
   from legitimate inline-math inequalities (``slopes $<$9%``), which are left
   untouched.
2. ``html.unescape`` the standard entities (lossless).

Real LaTeX math (``\frac``, ``\theta``, ``\textpm``, ``\textsuperscript``) is
**left as valid notation** — same category as inline math in any abstract.

Frontmatter ``title``/``abstract`` and the body ``# `` H1 also get LaTeX-dash
normalisation (``---`` → ``—``, ``--`` → ``–``); body prose does **not** (it can
contain CLI ``--flags`` in API-doc entries).

Every body is guarded: any digit lost during cleaning must originate inside a
removed ``<img>``/``<a>`` URL, else the body is skipped and reported. Touched
files are backed up; the catalog is rebuilt from the now-clean frontmatter.

Usage::

    python scripts/clean_paper_bodies.py            # dry-run (default)
    python scripts/clean_paper_bodies.py --apply    # write changes
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
from collections import Counter
from pathlib import Path

import frontmatter

from papermind.catalog.index import CatalogIndex
from papermind.catalog.render import render_catalog_md

# Escaped-HTML-tag junk. Anchored on a known tag name immediately after the
# escaped ``<`` so legitimate inline-math inequalities (``$<$9%``, ``(R2 $>$ 0.2)``)
# are never matched. ``a``/``img`` require attributes; simple tags must be
# followed directly by the closing delimiter.
_ESC_TAG = re.compile(
    r"\{?\$?<\$\}?"  # opening delimiter: {$<$} / $<$} / <$}
    r"/?(?:p|strong|br|q|a|img)\b"  # optional closing-slash + known tag name
    r'(?:\s+[a-zA-Z-]+="[^"$]*")*'  # optional quoted attributes (class=, href=, src=)
    r"\s*/?\s*"  # optional self-close slash
    r"\{?\$>\$?\}?"  # closing delimiter: {$>$} / $>$} / {$>
)
# img/anchor blobs whose attribute URLs legitimately carry digits we may drop.
_URL_TAG = re.compile(
    r"\{?\$?<\$\}?/?(?:a|img)\b"
    r'(?:\s+[a-zA-Z-]+="[^"$]*")*\s*/?\s*\{?\$>\$?\}?'
)
_NUM = re.compile(r"\d+\.?\d*")
# Brace-wrapped inline-math comparison operators the converter emitted for a
# literal ``<``/``>`` in text (``slopes {$<$}9%`` → ``slopes <9%``). Converted
# only when NOT followed by a letter, so we never forge a ``<tag``-looking span
# (the 2 ``{$<$}c.`` "circa" cases stay as valid inline math).
_LT = re.compile(r"\{\$<\$\}(?![A-Za-z])")
_GT = re.compile(r"\{\$>\$\}(?![A-Za-z])")
# Plain HTML structural tags (a real ``<table class="…">`` of content survives in
# some full-text OCR bodies). Anchored on a KNOWN tag name so it can't eat an
# inequality ``<`` or a number-bearing span — that anchoring is exactly why the
# greedy ``<[^>]+>`` of ``strip_html`` is unsafe here and this is not.
_HTML_STRUCT = re.compile(
    r"</?(?:table|thead|tbody|tr|th|td|br|div|span|ul|ol|li)\b[^>]*>"
)


def clean_body(text: str) -> str:
    """Strip escaped-HTML-tag junk, decode inline ``<``/``>`` + entities (no LaTeX)."""
    text = _ESC_TAG.sub("", text)
    text = _HTML_STRUCT.sub(" ", text)
    text = _GT.sub(">", _LT.sub("<", text))
    return html.unescape(text)


def normalize_dashes(text: str) -> str:
    """LaTeX dash convention: ``---`` → em-dash, ``--`` → en-dash."""
    return text.replace("---", "—").replace("--", "–")


def _clean_body_with_h1(content: str) -> str:
    """Clean the body, then dash-normalise its leading ``# `` H1 (mirrors title)."""
    cleaned = clean_body(content)
    lines = cleaned.split("\n")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if line.startswith("# "):
            lines[i] = "# " + normalize_dashes(line[2:])
        break
    return "\n".join(lines)


def _tag_attr_digits(text: str) -> list[str]:
    """Digits living inside removed tag attributes — URL blobs and structural-tag
    layout attributes (``colspan="14"``, ``border="1"``). These are markup, never
    scientific content, so their loss during cleaning is expected (multiset)."""
    out: list[str] = []
    for blob in _URL_TAG.findall(text):
        out.extend(_NUM.findall(blob))
    for blob in _HTML_STRUCT.findall(text):
        out.extend(_NUM.findall(blob))
    return out


def _body_safe(old: str, new: str) -> tuple[bool, list[str]]:
    """True iff every digit lost from the body came from removed tag markup.

    Genuine multiset diff: ``Counter(old) - Counter(new)`` is what actually went
    missing (a number recurring three times and losing one is one loss, not zero);
    subtracting digits that lived inside removed tag attributes (URLs, colspan…)
    leaves only unaccounted loss — which must be empty for the body to be cleaned.
    """
    lost = Counter(_NUM.findall(old)) - Counter(_NUM.findall(new))
    unaccounted = lost - Counter(_tag_attr_digits(old))
    return (not unaccounted), sorted(unaccounted.elements())


# (path, post, new_title|None, new_abstract|None, new_body|None)
Target = tuple[Path, frontmatter.Post, str | None, str | None, str | None]


def _find_targets(kb: Path) -> tuple[list[Target], list[tuple[str, list[str]]]]:
    """Collect repair records plus a list of bodies skipped for digit-loss."""
    targets: list[Target] = []
    skipped: list[tuple[str, list[str]]] = []
    for md in sorted((kb / "papers").rglob("paper.md")):
        try:
            post = frontmatter.load(md)
        except Exception:
            continue

        old_title = str(post.metadata.get("title", "") or "")
        new_title = normalize_dashes(old_title)
        title_changed = new_title != old_title

        old_abstract = str(post.metadata.get("abstract", "") or "")
        new_abstract = normalize_dashes(old_abstract)
        abstract_changed = new_abstract != old_abstract

        old_body = post.content
        new_body = _clean_body_with_h1(old_body)
        body_changed = new_body != old_body
        if body_changed:
            safe, lost = _body_safe(old_body, new_body)
            if not safe:
                skipped.append((md.parent.name, lost))
                new_body = None  # leave body untouched, keep frontmatter fixes
                body_changed = False

        if title_changed or abstract_changed or body_changed:
            targets.append(
                (
                    md,
                    post,
                    new_title if title_changed else None,
                    new_abstract if abstract_changed else None,
                    new_body if body_changed else None,
                )
            )
    return targets, skipped


def _print_dry_run(targets: list[Target], skipped: list[tuple[str, list[str]]]) -> None:
    """Summarise the planned clean with a residual audit and samples."""
    n_title = sum(1 for _, _, t, _, _ in targets if t is not None)
    n_abs = sum(1 for _, _, _, a, _ in targets if a is not None)
    n_body = sum(1 for _, _, _, _, b in targets if b is not None)
    print(
        f"{len(targets)} paper(s) to clean "
        f"({n_body} bodies + {n_title} title dashes + {n_abs} abstract dashes)\n"
    )
    if skipped:
        print(f"SKIPPED {len(skipped)} bodies (digit loss not from a URL blob):")
        for name, lost in skipped[:8]:
            print(f"  ! {name[:54]}  lost={lost[:6]}")
        print()

    # Residual audit: how much escaped junk remains after cleaning (should be the
    # legitimate inline-math $<$/$>$ inequalities we deliberately keep).
    shown = 0
    print("sample body cleans:")
    for md, post, _, _, new_body in targets:
        if new_body is None:
            continue
        old = post.content
        before = _ESC_TAG.findall(old)
        if not before:
            continue
        print(f"  [{md.parent.name[:50]}]  removed {len(before)} tag-blob(s)")
        shown += 1
        if shown >= 5:
            break
    print("\nDry-run only. Re-run with --apply to write.")


def _apply(kb: Path, targets: list[Target]) -> None:
    """Write cleaned bodies/frontmatter, back up first, then rebuild the catalog."""
    backup = kb / ".papermind" / "backups" / "clean_paper_bodies"
    backup.mkdir(parents=True, exist_ok=True)
    if (kb / "catalog.json").exists():
        shutil.copy2(kb / "catalog.json", backup / "catalog.json")
    db = kb / ".papermind" / "papermind.db"
    if db.exists():
        shutil.copy2(db, backup / "papermind.db")

    touched_fm = False
    for md, post, new_title, new_abstract, new_body in targets:
        dest = backup / md.relative_to(kb)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(md, dest)
        if new_title is not None:
            post["title"] = new_title
            touched_fm = True
        if new_abstract is not None:
            post["abstract"] = new_abstract
            touched_fm = True
        if new_body is not None:
            post.content = new_body
        md.write_text(
            frontmatter.dumps(post, sort_keys=False, allow_unicode=True) + "\n"
        )
    print(f"Cleaned {len(targets)} files. Backups: {backup}")

    if touched_fm:
        before = len(CatalogIndex(kb).entries)
        idx = CatalogIndex.rebuild(kb)
        after = len(idx.entries)
        if after != before:
            raise SystemExit(
                f"ABORT: entry count changed {before} -> {after}; restore from {backup}"
            )
        (kb / "catalog.md").write_text(render_catalog_md(idx.entries))
        print(f"Rebuilt catalog ({after} entries) + catalog.md.")
    print("Next: re-embed search index with `qmd update && qmd embed`.")


def main() -> None:
    """Run the body clean (dry-run unless ``--apply``)."""
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

    targets, skipped = _find_targets(kb)
    if not args.apply:
        _print_dry_run(targets, skipped)
        return
    if not targets:
        print("Nothing to do.")
        return
    if skipped:
        print(
            f"Note: {len(skipped)} bodies skipped for digit-loss (frontmatter fixed)."
        )
    _apply(kb, targets)


if __name__ == "__main__":
    main()
