"""API version diffing — track breaking changes across package versions.

Compares two versions of a package API ingested in the KB.  Works at
the level of extracted API markdown (``packages/<name>/api.md``),
parsing function signatures to detect additions, removals, and changes.

Usage::

    # Ingest two versions under different names
    papermind ingest package pandas --name pandas-2.1
    papermind ingest package pandas --name pandas-3.0

    # Diff them
    papermind api-diff pandas-2.1 pandas-3.0
    papermind api-diff pandas-2.1 pandas-3.0 --function DataFrame.to_parquet
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class FunctionSig:
    """A parsed function signature from API markdown."""

    name: str
    """Fully qualified function name."""
    params: list[str]
    """Parameter names."""
    full_signature: str
    """Raw signature string."""


@dataclass
class APIDiffEntry:
    """A single difference between two API versions."""

    kind: str
    """'added', 'removed', or 'changed'."""
    function: str
    """Function name."""
    detail: str
    """Human-readable description of the change."""


@dataclass
class APIDiffResult:
    """Result of comparing two package API versions."""

    old_name: str
    """Old package name in KB."""
    new_name: str
    """New package name in KB."""
    old_count: int
    """Number of functions in old version."""
    new_count: int
    """Number of functions in new version."""
    added: list[APIDiffEntry] = field(default_factory=list)
    """Functions added in new version."""
    removed: list[APIDiffEntry] = field(default_factory=list)
    """Functions removed in new version."""
    changed: list[APIDiffEntry] = field(default_factory=list)
    """Functions with changed signatures."""


# ---------------------------------------------------------------------------
# Signature parsing from API markdown
# ---------------------------------------------------------------------------

# Matches lines like: ### `function_name(param1, param2, **kwargs)`
_SIG_PATTERN = re.compile(
    r"^#{1,4}\s+`?(\w[\w.]*)\(([^)]*)\)`?\s*$",
    re.MULTILINE,
)

# Also matches: - **function_name**(param1, param2)
_ALT_SIG_PATTERN = re.compile(
    r"^\s*[-*]\s+\*?\*?(\w[\w.]*)\*?\*?\(([^)]*)\)",
    re.MULTILINE,
)


def _parse_signatures(api_text: str) -> dict[str, FunctionSig]:
    """Parse function signatures from API markdown.

    Args:
        api_text: Content of api.md file.

    Returns:
        Dict mapping function name to FunctionSig.
    """
    sigs: dict[str, FunctionSig] = {}

    for pattern in [_SIG_PATTERN, _ALT_SIG_PATTERN]:
        for m in pattern.finditer(api_text):
            name = m.group(1)
            raw_params = m.group(2)
            params = [
                p.strip().split(":")[0].split("=")[0].strip()
                for p in raw_params.split(",")
                if p.strip()
            ]
            if name not in sigs:
                sigs[name] = FunctionSig(
                    name=name,
                    params=params,
                    full_signature=f"{name}({raw_params})",
                )

    return sigs


# ---------------------------------------------------------------------------
# Diffing engine
# ---------------------------------------------------------------------------


def diff_apis(
    kb_path: Path,
    old_name: str,
    new_name: str,
    *,
    function_filter: str = "",
) -> APIDiffResult:
    """Compare two package API versions ingested in the KB.

    Args:
        kb_path: Knowledge base root.
        old_name: Old package name (e.g. 'pandas-2.1').
        new_name: New package name (e.g. 'pandas-3.0').
        function_filter: If provided, only show changes for this function.

    Returns:
        APIDiffResult with added/removed/changed entries.

    Raises:
        FileNotFoundError: If either package's api.md is not found.
    """
    old_api = _load_api_text(kb_path, old_name)
    new_api = _load_api_text(kb_path, new_name)

    old_sigs = _parse_signatures(old_api)
    new_sigs = _parse_signatures(new_api)

    # Filter if requested
    if function_filter:
        old_sigs = {k: v for k, v in old_sigs.items() if function_filter in k}
        new_sigs = {k: v for k, v in new_sigs.items() if function_filter in k}

    result = APIDiffResult(
        old_name=old_name,
        new_name=new_name,
        old_count=len(old_sigs),
        new_count=len(new_sigs),
    )

    old_names = set(old_sigs.keys())
    new_names = set(new_sigs.keys())

    # Added functions
    for name in sorted(new_names - old_names):
        result.added.append(
            APIDiffEntry("added", name, f"New: `{new_sigs[name].full_signature}`")
        )

    # Removed functions
    for name in sorted(old_names - new_names):
        result.removed.append(
            APIDiffEntry("removed", name, f"Was: `{old_sigs[name].full_signature}`")
        )

    # Changed signatures
    for name in sorted(old_names & new_names):
        old_sig = old_sigs[name]
        new_sig = new_sigs[name]

        if old_sig.params != new_sig.params:
            # Determine what changed
            old_set = set(old_sig.params)
            new_set = set(new_sig.params)
            added_params = new_set - old_set
            removed_params = old_set - new_set

            parts = []
            if added_params:
                parts.append(f"added params: {', '.join(sorted(added_params))}")
            if removed_params:
                parts.append(f"removed params: {', '.join(sorted(removed_params))}")
            if not parts:
                parts.append("parameter order changed")

            result.changed.append(APIDiffEntry("changed", name, "; ".join(parts)))

    return result


def _load_api_text(kb_path: Path, package_name: str) -> str:
    """Load api.md for a package from the KB."""
    api_path = kb_path / "packages" / package_name / "api.md"
    if not api_path.exists():
        raise FileNotFoundError(
            f"API file not found: {api_path}\n"
            f"Ingest the package first: papermind ingest package {package_name}"
        )
    return api_path.read_text()


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_api_diff(result: APIDiffResult) -> str:
    """Format API diff result as markdown."""
    total = len(result.added) + len(result.removed) + len(result.changed)

    lines = [
        f"## API Diff: {result.old_name} → {result.new_name}\n",
        f"- **Old:** {result.old_count} functions",
        f"- **New:** {result.new_count} functions",
        f"- **Changes:** {total} "
        f"({len(result.added)} added, {len(result.removed)} removed, "
        f"{len(result.changed)} changed)\n",
    ]

    if result.removed:
        lines.append("### Removed (breaking)\n")
        for e in result.removed:
            lines.append(f"- `{e.function}` — {e.detail}")

    if result.changed:
        lines.append("\n### Changed\n")
        for e in result.changed:
            lines.append(f"- `{e.function}` — {e.detail}")

    if result.added:
        lines.append("\n### Added\n")
        for e in result.added:
            lines.append(f"- `{e.function}` — {e.detail}")

    if total == 0:
        lines.append("No differences found.")

    return "\n".join(lines)
