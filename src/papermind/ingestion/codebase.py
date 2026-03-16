"""Codebase tree walker — multi-language signature extraction.

Walks a directory tree, respects .gitignore patterns, detects programming
languages by file extension, and extracts function/class/subroutine signatures
via per-language regex patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SignatureInfo:
    """A function/class/subroutine signature extracted from source."""

    name: str
    kind: str  # "function", "class", "subroutine", "module", etc.
    line: int
    docstring: str = ""


@dataclass
class CodebaseMap:
    """Result of walking a codebase."""

    name: str
    root: Path
    languages: set[str]
    file_tree: list[str]  # relative paths
    signatures: dict[str, list[SignatureInfo]]  # filename → signatures
    readme_content: str | None = None


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_EXT_TO_LANGUAGE: dict[str, str] = {
    ".f90": "fortran",
    ".f": "fortran",
    ".f77": "fortran",
    ".for": "fortran",
    ".py": "python",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".js": "javascript",
    ".ts": "typescript",
}


def _detect_language(path: Path) -> str | None:
    """Return the language name for a file extension, or None if unknown."""
    return _EXT_TO_LANGUAGE.get(path.suffix.lower())


# ---------------------------------------------------------------------------
# .gitignore pattern matching
# ---------------------------------------------------------------------------


def _load_gitignore_patterns(root: Path) -> list[str]:
    """Load patterns from .gitignore at *root*, if present.

    Returns a list of raw pattern strings (not yet normalised).
    """
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return []
    patterns: list[str] = []
    for line in gitignore.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        # Skip blank lines and comments
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _is_ignored(rel_path: str, patterns: list[str]) -> bool:
    """Return True if *rel_path* (forward-slash-separated) matches any pattern.

    Handles the two most common .gitignore forms that cover the vast majority
    of real files:

    1. ``name/`` — matches a directory component exactly.
    2. ``*.ext`` or ``name`` — matched against each path component, and also
       against the full relative path via fnmatch.
    """
    parts = rel_path.replace("\\", "/").split("/")
    for pattern in patterns:
        # Directory pattern: "foo/" — match any component named "foo"
        if pattern.endswith("/"):
            dir_name = pattern.rstrip("/")
            if dir_name in parts[:-1]:  # only directory components
                return True
            # Also match the last component if it is a directory name in rel_path
            if dir_name in parts:
                return True
        else:
            # Match each individual path component
            for part in parts:
                if fnmatch(part, pattern):
                    return True
            # Also match the full relative path
            if fnmatch(rel_path, pattern):
                return True
    return False


# ---------------------------------------------------------------------------
# Per-language signature extraction
# ---------------------------------------------------------------------------

# Each entry: (pattern, kind_group_index, name_group_index)
# group indices are 1-based capture groups in the regex.
_LANG_PATTERNS: dict[str, list[tuple[re.Pattern[str], str, int]]] = {
    "fortran": [
        (re.compile(r"^\s*(subroutine)\s+(\w+)", re.IGNORECASE), "subroutine", 2),
        (re.compile(r"^\s*(function)\s+(\w+)", re.IGNORECASE), "function", 2),
        (re.compile(r"^\s*(module)\s+(\w+)", re.IGNORECASE), "module", 2),
    ],
    "python": [
        (re.compile(r"^\s*(def)\s+(\w+)"), "function", 2),
        (re.compile(r"^\s*(class)\s+(\w+)"), "class", 2),
    ],
    "c": [
        # Simplified: return-type name(  — at least two tokens before the paren
        (re.compile(r"^\s*[\w\*]+\s+([\w\*]+)\s*\("), "function", 1),
    ],
    "cpp": [
        (re.compile(r"^\s*[\w\*:<>]+\s+([\w\*]+)\s*\("), "function", 1),
        (re.compile(r"^\s*(class|struct)\s+(\w+)"), "class", 2),
    ],
    "rust": [
        (re.compile(r"^\s*(?:pub\s+)?(fn)\s+(\w+)"), "function", 2),
        (re.compile(r"^\s*(?:pub\s+)?(struct)\s+(\w+)"), "struct", 2),
        (re.compile(r"^\s*(?:pub\s+)?(impl)\s+(\w+)"), "impl", 2),
    ],
    "go": [
        (re.compile(r"^\s*func\s+(?:\([\w\s\*]+\)\s+)?(\w+)\s*\("), "function", 1),
    ],
    "java": [
        (
            re.compile(
                r"^\s*(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\("
            ),
            "method",
            1,
        ),
        (re.compile(r"^\s*(?:public|private|protected|\s)*class\s+(\w+)"), "class", 1),
    ],
    "javascript": [
        (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function", 1),
        (re.compile(r"^\s*(?:export\s+)?class\s+(\w+)"), "class", 1),
        (
            re.compile(r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\("),
            "function",
            1,
        ),
    ],
    "typescript": [
        (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function", 1),
        (re.compile(r"^\s*(?:export\s+)?class\s+(\w+)"), "class", 1),
        (re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)"), "interface", 1),
        (
            re.compile(r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\("),
            "function",
            1,
        ),
    ],
}


def _extract_leading_comment(lines: list[str], sig_line_idx: int, language: str) -> str:
    """Return the leading comment block immediately above *sig_line_idx*.

    Scans upward from the line before the signature, collecting consecutive
    comment lines.  Empty lines break the block.
    """
    comment_prefixes: dict[str, tuple[str, ...]] = {
        "fortran": ("!",),
        "python": ("#", '"""', "'''"),
        "c": ("//", "/*", " *"),
        "cpp": ("//", "/*", " *"),
        "rust": ("///", "//", "/*", " *"),
        "go": ("//",),
        "java": ("//", "/*", " *", "/**"),
        "javascript": ("//", "/*", " *"),
        "typescript": ("//", "/*", " *"),
    }
    prefixes = comment_prefixes.get(language, ("//", "#", "!"))

    collected: list[str] = []
    idx = sig_line_idx - 1
    while idx >= 0:
        stripped = lines[idx].strip()
        if not stripped:
            break
        if any(stripped.startswith(p) for p in prefixes):
            collected.append(stripped)
            idx -= 1
        else:
            break

    return " ".join(reversed(collected))


def _extract_signatures(path: Path, language: str) -> list[SignatureInfo]:
    """Extract signatures from *path* using the language's regex patterns."""
    patterns = _LANG_PATTERNS.get(language)
    if not patterns:
        return []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = text.splitlines()
    sigs: list[SignatureInfo] = []

    for line_idx, line in enumerate(lines):
        for compiled, kind, name_group in patterns:
            m = compiled.match(line)
            if m:
                name = m.group(name_group)
                docstring = _extract_leading_comment(lines, line_idx, language)
                sigs.append(
                    SignatureInfo(
                        name=name,
                        kind=kind,
                        line=line_idx + 1,  # 1-based
                        docstring=docstring,
                    )
                )
                break  # only first matching pattern per line

    return sigs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def walk_codebase(root: Path) -> CodebaseMap:
    """Walk *root*, extract signatures, respect .gitignore, detect languages.

    Args:
        root: Absolute path to the codebase root directory.

    Returns:
        A :class:`CodebaseMap` with language set, file tree, signatures, and
        README content if present.
    """
    gitignore_patterns = _load_gitignore_patterns(root)

    languages: set[str] = set()
    file_tree: list[str] = []
    signatures: dict[str, list[SignatureInfo]] = {}
    readme_content: str | None = None

    for abs_path in sorted(root.rglob("*")):
        if abs_path.is_dir():
            continue

        rel = abs_path.relative_to(root)
        rel_str = str(rel)

        if _is_ignored(rel_str, gitignore_patterns):
            continue

        file_tree.append(rel_str)

        # README detection (case-insensitive, any extension)
        if abs_path.stem.upper() == "README":
            try:
                readme_content = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass

        language = _detect_language(abs_path)
        if language:
            languages.add(language)
            sigs = _extract_signatures(abs_path, language)
            if sigs:
                signatures[rel_str] = sigs

    return CodebaseMap(
        name=root.name,
        root=root,
        languages=languages,
        file_tree=file_tree,
        signatures=signatures,
        readme_content=readme_content,
    )
