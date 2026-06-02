"""Normalise text-mode LaTeX symbols in PaperMind ``paper.md`` bodies.

After the title/abstract decode and the HTML-tag body clean
(``scripts/clean_paper_bodies.py``), the *body* of many bib-shim papers still
carries text-mode LaTeX symbol commands — ``\\textpm``, ``\\texttimes``,
``\\textasciitilde``, ``\\textsuperscript{2}``, ``\\textsuperscript{137}`` and
friends. ``qmd`` indexes the full body, so ``yield of 0.57 km\\textsuperscript{2}``
or ``12.3\\textpm0.4`` leaks into search snippets reading exactly as junk as the
escaped HTML tags did. The frontmatter is already clean (the title sweep's
``latex_to_text`` rendered these in title/abstract), so this is **body-only**.

This is the same snippet-junk class as ``clean_paper_bodies.py`` — and the same
inconsistency it would otherwise leave: that cleaner converted ``{$<$}`` → ``<``
but left ``\\textpm``, both equally-simple operators. This pass closes that gap.

**Why a separate, string-only pass (not ``latex_to_text``):** ``%`` is a LaTeX
comment char; ``latex_to_text`` silently drops everything from the first ``%`` to
end-of-line (a glacier abstract lost its entire shrinkage-rate statistics this
way last session). A fixed substitution table cannot hit the ``%`` problem, so
it is as safe as the earlier operator pass.

The transform is a fixed 1:1 table:

* **Arg-less symbols** → their Unicode glyph (``\\textpm`` → ``±``,
  ``\\texttimes`` → ``×``, ``\\textasciitilde`` → ``~`` …).
* **``\\textsuperscript{X}`` / ``\\textsubscript{X}``** → Unicode super/subscript
  **iff** every char in ``X`` has a super/subscript form (digits, signs, and the
  subscriptable letters). ``{2}`` → ``²``, ``{-1}`` → ``⁻¹``, ``{137}`` → ``¹³⁷``,
  ``{xs}`` → ``ₓₛ``. **Non-numeric/unmappable args are left untouched** —
  footnote-affiliation markers (``\\textsuperscript{a,b,c}``) and the one
  ``\\textsuperscript{{$\\circ$}}`` (real inline math) are *not* force-mapped.

Real math structures (``\\frac``, ``\\theta``, ``\\sum``, ``\\textcircled{…}``)
are **left as valid notation** — decoding those is exactly the unsafe territory
this pass avoids.

Every body is guarded: the digit multiset (folding super/subscript digits back to
ASCII) must be **identical** before and after — a representation change
(``137`` → ``¹³⁷``) reads as preserved, an actual deletion trips the guard and
skips the body. The transform is **idempotent** (re-running finds nothing).
Touched files are backed up; the catalog is untouched (frontmatter unchanged).

Usage::

    python scripts/normalize_text_symbols.py            # dry-run (default)
    python scripts/normalize_text_symbols.py --apply    # write changes
"""

from __future__ import annotations

import argparse
import re
import shutil
from collections import Counter
from pathlib import Path

import frontmatter

# Arg-less text-mode symbols → Unicode glyph. Only the commands actually present
# in the corpus (verified) plus the canonical µ/°, all zero-risk 1:1 mappings.
_SYMBOLS = {
    r"\textpm": "±",
    r"\texttimes": "×",
    r"\textasciitilde": "~",
    r"\textbackslash": "\\",
    r"\textsurd": "√",
    r"\textasciicircum": "^",
    r"\textasciimacron": "¯",
    r"\texttheta": "θ",
    r"\textasciiacute": "´",
    r"\textmu": "µ",
    r"\textdegree": "°",
}
# Match a command name only when not followed by another letter (so ``\textpm``
# never bites into a longer ``\textpmx``). Longest-first alternation. An optional
# trailing empty group ``{}`` (LaTeX no-op the converter often emits, e.g.
# ``\texttimes{}``) is consumed so the glyph is left clean (``×`` not ``×{}``).
_SYMBOL_RE = re.compile(
    r"("
    + "|".join(re.escape(k) for k in sorted(_SYMBOLS, key=len, reverse=True))
    + r")(?![a-zA-Z])(?:\{\})?"
)

# Super/subscript translation. ``−`` (U+2212) and ``-`` both fold to the minus form.
_SUP = str.maketrans("0123456789+-−=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ⁿ")
_SUB = str.maketrans(
    "0123456789+-−=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"
)
_SUP_OK = set("0123456789+-−=()n")
_SUB_OK = set("0123456789+-−=()aehijklmnoprstuvx")

_SUPER_RE = re.compile(r"\\textsuperscript\{([^{}]*)\}")
_SUB_RE = re.compile(r"\\textsubscript\{([^{}]*)\}")

# Digit guard: fold super/subscript digits back to ASCII, then a representation
# change (137 -> ¹³⁷) counts as preserved while a real deletion does not.
_FOLD = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉", "01234567890123456789")
_DIGIT = re.compile(r"[0-9]")


def _sup_repl(m: re.Match[str]) -> str:
    arg = m.group(1)
    return arg.translate(_SUP) if arg and all(c in _SUP_OK for c in arg) else m.group(0)


def _sub_repl(m: re.Match[str]) -> str:
    arg = m.group(1)
    return arg.translate(_SUB) if arg and all(c in _SUB_OK for c in arg) else m.group(0)


def normalize_symbols(text: str) -> str:
    """Apply the fixed text-symbol table (arg-less + numeric super/subscript)."""
    text = _SYMBOL_RE.sub(lambda m: _SYMBOLS[m.group(1)], text)
    text = _SUPER_RE.sub(_sup_repl, text)
    text = _SUB_RE.sub(_sub_repl, text)
    return text


def _digits(s: str) -> Counter[str]:
    """ASCII-digit multiset with super/subscript digits folded back to ASCII."""
    return Counter(_DIGIT.findall(s.translate(_FOLD)))


def _safe(old: str, new: str) -> bool:
    """True iff no digit was lost (representation changes fold to equality) and the
    transform is idempotent (re-applying it to the result is a no-op)."""
    return _digits(old) == _digits(new) and normalize_symbols(new) == new


# (path, new_body)
Target = tuple[Path, str]


def _find_targets(kb: Path) -> tuple[list[Target], list[str]]:
    """Collect bodies to rewrite plus a list of bodies skipped for digit-loss."""
    targets: list[Target] = []
    skipped: list[str] = []
    for md in sorted((kb / "papers").rglob("paper.md")):
        try:
            post = frontmatter.load(md)
        except Exception:
            continue
        old = post.content
        new = normalize_symbols(old)
        if new == old:
            continue
        if not _safe(old, new):
            skipped.append(md.parent.name)
            continue
        targets.append((md, new))
    return targets, skipped


def _residual(kb: Path) -> Counter[str]:
    """Text-mode commands that remain after this pass (the documented tail:
    lettered footnote-superscripts, ``\\textcircled{…}``, math)."""
    out: Counter[str] = Counter()
    pat = re.compile(r"\\text[a-z]+")
    for md in sorted((kb / "papers").rglob("paper.md")):
        try:
            body = frontmatter.load(md).content
        except Exception:
            continue
        out.update(pat.findall(normalize_symbols(body)))
    return out


def _print_dry_run(kb: Path, targets: list[Target], skipped: list[str]) -> None:
    """Summarise the planned normalisation with a residual audit and samples."""
    print(f"{len(targets)} body(ies) to normalise (text-mode LaTeX symbols)\n")
    if skipped:
        print(f"SKIPPED {len(skipped)} bodies (digit multiset changed):")
        for name in skipped[:8]:
            print(f"  ! {name[:64]}")
        print()
    shown = 0
    print("sample normalisations (first changed line):")
    for md, new in targets:
        try:
            old = frontmatter.load(md).content
        except Exception:
            continue
        for a, b in zip(old.split("\n"), new.split("\n")):
            if a != b:
                name = md.parent.name[:40]
                print(f"  [{name}]\n     - {a.strip()[:80]}\n     + {b.strip()[:80]}")
                shown += 1
                break
        if shown >= 5:
            break
    print("\nresidual \\text… AFTER this pass (documented tail — footnote / math):")
    res = _residual(kb)
    for cmd, n in res.most_common(12):
        print(f"  {n:4d}  {cmd}")
    print("\nDry-run only. Re-run with --apply to write.")


def _apply(kb: Path, targets: list[Target]) -> None:
    """Write normalised bodies, backing each up first. Frontmatter untouched →
    catalog needs no rebuild."""
    backup = kb / ".papermind" / "backups" / "normalize_text_symbols"
    backup.mkdir(parents=True, exist_ok=True)
    for md, new in targets:
        dest = backup / md.relative_to(kb)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(md, dest)
        post = frontmatter.load(md)
        post.content = new
        md.write_text(
            frontmatter.dumps(post, sort_keys=False, allow_unicode=True) + "\n"
        )
    print(f"Normalised {len(targets)} bodies. Backups: {backup}")
    print("Catalog untouched (frontmatter unchanged).")
    print("Next: re-embed search index with `qmd update && qmd embed`.")


def main() -> None:
    """Run the text-symbol normalisation (dry-run unless ``--apply``)."""
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
        _print_dry_run(kb, targets, skipped)
        return
    if not targets:
        print("Nothing to do.")
        return
    if skipped:
        print(f"Note: {len(skipped)} bodies skipped for digit-loss (left untouched).")
    _apply(kb, targets)


if __name__ == "__main__":
    main()
