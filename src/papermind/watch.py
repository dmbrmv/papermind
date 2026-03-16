"""Watch — extract concepts from a source file and find relevant KB entries."""

from __future__ import annotations

import ast
import re
from pathlib import Path

# Python stdlib/builtins to ignore as search terms
_CODE_STOPWORDS = frozenset(
    "os sys re json math pathlib typing collections dataclasses "
    "functools itertools logging abc enum copy datetime time "
    "argparse subprocess shutil tempfile io textwrap warnings "
    "unittest pytest mock patch fixture assert return yield "
    "self cls none true false int float str list dict set tuple "
    "bool bytes type object range len print open path file "
    "import from class def async await try except finally raise "
    "if else elif for while break continue pass lambda with as "
    "and or not in is None True False".split()
)

_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _split_identifier(name: str) -> list[str]:
    """Split CamelCase and snake_case into words."""
    # CamelCase → separate words
    parts = _CAMEL_RE.sub("_", name).lower().split("_")
    return [p for p in parts if len(p) > 2 and p not in _CODE_STOPWORDS]


def extract_concepts(source_path: Path) -> list[str]:
    """Parse a Python file and extract concept terms.

    Extracts import names, class/function names, and docstrings.
    Returns deduplicated terms sorted by likely relevance.

    Args:
        source_path: Path to a Python source file.

    Returns:
        List of concept terms (lowercase, deduplicated).
    """
    try:
        source = source_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    terms: list[str] = []

    # AST-based extraction for Python files
    if source_path.suffix == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # Fall back to regex for unparseable files
            return _regex_extract(source)

        for node in ast.walk(tree):
            # Imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    terms.extend(_split_identifier(alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    terms.extend(_split_identifier(node.module))
                for alias in node.names:
                    terms.extend(_split_identifier(alias.name))

            # Class and function names
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                terms.extend(_split_identifier(node.name))
                # First docstring
                ds = ast.get_docstring(node)
                if ds:
                    terms.extend(_extract_doc_terms(ds))
            elif isinstance(node, ast.ClassDef):
                terms.extend(_split_identifier(node.name))
                ds = ast.get_docstring(node)
                if ds:
                    terms.extend(_extract_doc_terms(ds))
    else:
        # Non-Python: regex fallback
        terms.extend(_regex_extract(source))

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in terms:
        if t not in seen and t not in _CODE_STOPWORDS:
            seen.add(t)
            unique.append(t)
    return unique


def _extract_doc_terms(docstring: str) -> list[str]:
    """Extract meaningful terms from a docstring."""
    words = re.findall(r"[a-z][a-z0-9_-]{2,}", docstring.lower())
    return [w for w in words[:20] if w not in _CODE_STOPWORDS]


def _regex_extract(source: str) -> list[str]:
    """Fallback concept extraction via regex (non-Python files)."""
    # Extract words from comments and string literals
    comments = re.findall(r"#\s*(.+)$", source, re.MULTILINE)
    words: list[str] = []
    for comment in comments:
        words.extend(
            w
            for w in re.findall(r"[a-z][a-z0-9_-]{2,}", comment.lower())
            if w not in _CODE_STOPWORDS
        )
    return words


def watch_file(
    source_path: Path,
    kb_path: Path,
    *,
    limit: int = 5,
) -> list:
    """Extract concepts from a source file and search the KB.

    Args:
        source_path: Path to the source code file.
        kb_path: Knowledge base root.
        limit: Max results to return.

    Returns:
        List of SearchResult objects from fallback_search.
    """
    from papermind.query.fallback import fallback_search

    concepts = extract_concepts(source_path)
    if not concepts:
        return []

    query = " ".join(concepts[:30])  # cap query length
    return fallback_search(kb_path, query, limit=limit)


def format_watch_output(source_name: str, results: list) -> str:
    """Format watch results in compact scan-tier style."""
    if not results:
        return f"# watch: {source_name} → no matches"

    lines = [f"# watch: {source_name} → {len(results)} match(es)"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r.score:.1f}] {r.title} — {r.path}")
    return "\n".join(lines)
