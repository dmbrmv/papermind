"""Implementation verification — does the code match the paper?

Orchestrates equation-map + provenance to produce a structured
verification report: symbol coverage, confidence score, and gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VerificationResult:
    """Structured result of verifying code against a paper equation."""

    paper_id: str
    """Paper identifier."""
    paper_title: str
    """Paper title."""
    equation_number: str
    """Equation number being verified."""
    equation_latex: str
    """LaTeX of the equation."""
    file_path: str
    """Source file path."""
    function_name: str
    """Function being verified."""
    coverage: float
    """Fraction of equation symbols matched to code (0-1)."""
    avg_confidence: float
    """Average confidence of matched symbols (0-1)."""
    verdict: str
    """'good', 'partial', 'poor', or 'no_data'."""
    mappings: list[dict] = field(default_factory=list)
    """Symbol→variable mappings with confidence."""
    unmatched_symbols: list[str] = field(default_factory=list)
    """Equation symbols with no code match."""
    unmatched_variables: list[str] = field(default_factory=list)
    """Code variables with no equation symbol."""
    provenance_refs: list[dict] = field(default_factory=list)
    """# REF: annotations found in the code file."""


def verify_implementation(
    paper_id: str,
    equation_number: str,
    source_path: Path,
    function_name: str | None,
    kb_path: Path,
) -> VerificationResult:
    """Verify that code implements a paper equation correctly.

    Loads the equation from the KB, extracts code variables, runs the
    heuristic matcher, and scores the alignment.

    Args:
        paper_id: Paper ID in the KB.
        equation_number: Equation number (e.g. '4.2').
        source_path: Path to the source file.
        function_name: Optional function to scope.
        kb_path: Knowledge base root.

    Returns:
        VerificationResult with coverage, confidence, and gaps.
    """
    from papermind.equation_map import map_equation_to_code
    from papermind.provenance import extract_provenance

    # Load equation from paper
    latex, title = _load_equation(paper_id, equation_number, kb_path)
    if not latex:
        return VerificationResult(
            paper_id=paper_id,
            paper_title=title,
            equation_number=equation_number,
            equation_latex="",
            file_path=str(source_path),
            function_name=function_name or "(all)",
            coverage=0.0,
            avg_confidence=0.0,
            verdict="no_data",
        )

    # Run equation-to-code mapping
    map_result = map_equation_to_code(
        latex, source_path, function_name, equation_number=equation_number
    )

    # Extract provenance annotations from the file
    prov_refs = extract_provenance(source_path)
    prov_dicts = [
        {"line": r.line, "identifier": r.identifier, "location": r.location}
        for r in prov_refs
    ]

    # Calculate coverage and confidence
    total_symbols = len(map_result.mappings) + len(map_result.unmatched_symbols)
    coverage = len(map_result.mappings) / total_symbols if total_symbols > 0 else 0.0

    avg_confidence = 0.0
    if map_result.mappings:
        avg_confidence = sum(m.confidence for m in map_result.mappings) / len(
            map_result.mappings
        )

    # Determine verdict
    if total_symbols == 0:
        verdict = "no_data"
    elif coverage >= 0.8 and avg_confidence >= 0.7:
        verdict = "good"
    elif coverage >= 0.5:
        verdict = "partial"
    else:
        verdict = "poor"

    return VerificationResult(
        paper_id=paper_id,
        paper_title=title,
        equation_number=equation_number,
        equation_latex=latex,
        file_path=str(source_path),
        function_name=function_name or "(all)",
        coverage=coverage,
        avg_confidence=avg_confidence,
        verdict=verdict,
        mappings=[
            {
                "symbol": m.symbol,
                "variable": m.variable,
                "confidence": m.confidence,
                "method": m.method,
            }
            for m in map_result.mappings
        ],
        unmatched_symbols=map_result.unmatched_symbols,
        unmatched_variables=map_result.unmatched_variables,
        provenance_refs=prov_dicts,
    )


def _load_equation(
    paper_id: str, equation_number: str, kb_path: Path
) -> tuple[str, str]:
    """Load an equation from the KB by paper ID and number.

    Returns:
        Tuple of (latex, paper_title). Empty latex if not found.
    """
    import frontmatter as fm_lib

    papers_dir = kb_path / "papers"
    if not papers_dir.exists():
        return "", ""

    for md_file in papers_dir.rglob("paper.md"):
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("id") != paper_id:
                continue

            title = post.metadata.get("title", "")
            equations = post.metadata.get("equations", [])
            for eq in equations:
                if eq.get("number") == equation_number:
                    return eq["latex"], title

            return "", title
        except Exception:
            continue

    return "", ""


def format_verification(result: VerificationResult) -> str:
    """Format a verification result as markdown.

    Args:
        result: VerificationResult to format.

    Returns:
        Formatted markdown string.
    """
    verdict_emoji = {
        "good": "[green]PASS[/green]",
        "partial": "[yellow]PARTIAL[/yellow]",
        "poor": "[red]FAIL[/red]",
        "no_data": "[dim]NO DATA[/dim]",
    }

    lines = [
        f"## Verification: {result.paper_title or result.paper_id}\n",
        f"**Equation {result.equation_number}:** `{result.equation_latex}`"
        if result.equation_latex
        else f"**Equation {result.equation_number}:** (not found in KB)",
        f"**Code:** `{result.file_path}::{result.function_name}`",
        f"**Verdict:** {verdict_emoji.get(result.verdict, result.verdict)}",
        f"**Coverage:** {result.coverage:.0%} of symbols matched",
        f"**Avg confidence:** {result.avg_confidence:.0%}",
    ]

    if result.mappings:
        lines.append("\n### Symbol Mappings\n")
        lines.append("| Symbol | Variable | Confidence | Method |")
        lines.append("|--------|----------|------------|--------|")
        for m in result.mappings:
            lines.append(
                f"| `{m['symbol']}` | `{m['variable']}` "
                f"| {m['confidence']:.0%} | {m['method']} |"
            )

    if result.unmatched_symbols:
        lines.append("\n### Gaps (equation symbols not in code)\n")
        for s in result.unmatched_symbols:
            lines.append(f"- `{s}`")

    if result.provenance_refs:
        lines.append("\n### Provenance Annotations\n")
        for r in result.provenance_refs:
            loc = f" {r['location']}" if r.get("location") else ""
            lines.append(f"- L{r['line']}: {r['identifier']}{loc}")

    return "\n".join(lines)
