"""Equation-to-code mapping — heuristic symbol↔variable matching.

No LLM dependency. Extracts symbols from LaTeX equations and variables
from source code, then matches them using name similarity, abbreviation
expansion, and glossary lookup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SymbolMapping:
    """A proposed mapping between a LaTeX symbol and a code variable."""

    symbol: str
    """LaTeX symbol (e.g. 'Q', 'K_s', 'alpha_{bf}')."""
    variable: str
    """Code variable name (e.g. 'discharge', 'sol_k', 'alpha_bf')."""
    confidence: float
    """Match confidence 0-1."""
    method: str
    """How the match was found: 'exact', 'normalized', 'glossary', 'fuzzy'."""


@dataclass
class EquationMapResult:
    """Result of mapping an equation to code."""

    equation_latex: str
    """The LaTeX equation being mapped."""
    equation_number: str
    """Equation number (e.g. '4.2'), or empty."""
    function_name: str
    """Code function being mapped to."""
    file_path: str
    """Source file path."""
    mappings: list[SymbolMapping] = field(default_factory=list)
    """Proposed symbol→variable mappings."""
    unmatched_symbols: list[str] = field(default_factory=list)
    """Equation symbols with no code match."""
    unmatched_variables: list[str] = field(default_factory=list)
    """Code variables with no equation match."""


# ---------------------------------------------------------------------------
# LaTeX symbol extraction
# ---------------------------------------------------------------------------

# Common LaTeX commands that are operators/functions, not symbols
_LATEX_OPERATORS = frozenset(
    {
        "frac",
        "sum",
        "int",
        "prod",
        "partial",
        "nabla",
        "sqrt",
        "log",
        "ln",
        "exp",
        "sin",
        "cos",
        "tan",
        "max",
        "min",
        "lim",
        "left",
        "right",
        "cdot",
        "times",
        "text",
        "mathrm",
        "mathbf",
        "mathbb",
        "begin",
        "end",
        "quad",
        "qquad",
        "leq",
        "geq",
        "neq",
        "approx",
        "infty",
        "forall",
        "exists",
        "in",
        "over",
        "bmod",
    }
)

# LaTeX → common code name mappings (built-in, no glossary needed)
_LATEX_TO_CODE: dict[str, list[str]] = {
    "alpha": ["alpha", "a"],
    "beta": ["beta", "b"],
    "gamma": ["gamma", "g"],
    "delta": ["delta", "d", "dt"],
    "epsilon": ["epsilon", "eps"],
    "theta": ["theta"],
    "lambda": ["lambda_", "lam"],  # lambda is reserved in Python
    "mu": ["mu"],
    "sigma": ["sigma", "std"],
    "omega": ["omega", "w"],
    "phi": ["phi"],
    "psi": ["psi"],
    "rho": ["rho", "density"],
    "tau": ["tau"],
    "eta": ["eta"],
    "kappa": ["kappa", "k"],
    "Delta": ["delta", "change"],
}


def extract_latex_symbols(latex: str) -> list[str]:
    """Extract mathematical symbols from a LaTeX equation.

    Identifies variable names, Greek letters, and subscripted symbols.
    Filters out operators and common LaTeX commands.

    Args:
        latex: Raw LaTeX string (without $$ delimiters).

    Returns:
        List of unique symbol strings.
    """
    symbols: set[str] = set()

    # Greek letters: \alpha, \beta, etc.
    for m in re.finditer(r"\\([a-zA-Z]+)", latex):
        name = m.group(1)
        if name not in _LATEX_OPERATORS:
            symbols.add(name)

    # Subscripted symbols: X_{sub} or X_s
    for m in re.finditer(r"([A-Za-z])_\{([^}]+)\}", latex):
        base = m.group(1)
        sub = m.group(2)
        symbols.add(f"{base}_{sub}")
    for m in re.finditer(r"([A-Za-z])_([A-Za-z0-9])\b", latex):
        base = m.group(1)
        sub = m.group(2)
        symbols.add(f"{base}_{sub}")

    # Standalone Latin letters (single uppercase or specific lowercase)
    for m in re.finditer(r"\b([A-Z])\b", latex):
        symbols.add(m.group(1))
    # Also catch lowercase variables that aren't part of commands
    cleaned = re.sub(r"\\[a-zA-Z]+", " ", latex)  # remove commands
    cleaned = re.sub(r"_\{[^}]*\}", "", cleaned)  # remove subscripts (handled above)
    for m in re.finditer(r"\b([a-z])\b", cleaned):
        ch = m.group(1)
        if ch not in {"d", "e", "i"}:  # skip differentials, euler, imaginary
            symbols.add(ch)

    return sorted(symbols)


def extract_code_variables(
    source_path: Path,
    function_name: str | None = None,
) -> list[str]:
    """Extract variable names from a source file or specific function.

    Args:
        source_path: Path to the source file.
        function_name: If provided, only extract from this function.

    Returns:
        List of unique variable names.
    """
    try:
        text = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if source_path.suffix == ".py":
        return _extract_python_variables(text, function_name)

    # Fallback: regex for assignments in any language
    return _extract_generic_variables(text, function_name)


def _extract_python_variables(text: str, function_name: str | None) -> list[str]:
    """Extract variables from Python source using AST."""
    import ast

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _extract_generic_variables(text, function_name)

    variables: set[str] = set()

    for node in ast.walk(tree):
        # Find the target function
        if function_name and isinstance(node, ast.FunctionDef):
            if node.name != function_name:
                continue
            # Extract from this function's body
            for child in ast.walk(node):
                if isinstance(child, ast.arg):
                    variables.add(child.arg)
                elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    variables.add(child.id)
            return sorted(variables - {"self", "cls"})

        # No function filter — extract all assignments
        if not function_name:
            if isinstance(node, ast.arg):
                variables.add(node.arg)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                variables.add(node.id)

    return sorted(variables - {"self", "cls"})


def _extract_generic_variables(text: str, function_name: str | None) -> list[str]:
    """Regex-based variable extraction for non-Python files."""
    variables: set[str] = set()

    # Simple assignment patterns
    for m in re.finditer(r"\b([a-zA-Z_]\w*)\s*=\s*", text):
        variables.add(m.group(1))

    # Fortran declarations
    for m in re.finditer(
        r"(?:real|integer|double\s+precision|character)\s*(?:::)?\s*(\w+)",
        text,
        re.IGNORECASE,
    ):
        variables.add(m.group(1))

    # Function/subroutine arguments
    for m in re.finditer(
        r"(?:def|subroutine|function)\s+\w+\s*\(([^)]*)\)",
        text,
        re.IGNORECASE,
    ):
        for arg in m.group(1).split(","):
            arg = arg.strip().split(":")[-1].strip().split("=")[0].strip()
            if arg and arg.isidentifier():
                variables.add(arg)

    return sorted(variables)


# ---------------------------------------------------------------------------
# Matching engine
# ---------------------------------------------------------------------------


def _normalize_symbol(symbol: str) -> str:
    """Normalize a LaTeX symbol for comparison.

    Converts subscript notation to underscore: K_{sat} → k_sat, alpha_{bf} → alpha_bf.
    """
    # Remove braces: K_{sat} → K_sat
    result = symbol.replace("{", "").replace("}", "")
    return result.lower()


def _load_symbol_glossary() -> dict[str, list[str]]:
    """Load the glossary for symbol → variable name expansion."""
    import yaml

    glossary_path = Path(__file__).parent / "glossary.yaml"
    if not glossary_path.exists():
        return {}

    with open(glossary_path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return {}

    # Build symbol → code variable mapping from glossary entries
    mapping: dict[str, list[str]] = {}
    for key, entry in data.items():
        name = entry.get("name", "")
        # The glossary key itself is often the code variable name
        mapping[key.lower()] = [key.lower()]
        # Also map from the full name words
        if name:
            words = [w.lower() for w in name.split() if len(w) > 2]
            mapping[key.lower()].extend(words)

    return mapping


def match_symbols_to_variables(
    symbols: list[str],
    variables: list[str],
) -> tuple[list[SymbolMapping], list[str], list[str]]:
    """Match equation symbols to code variables.

    Uses four strategies in order:
    1. Exact match (case-insensitive)
    2. Normalized match (subscript→underscore)
    3. Glossary expansion (α → alpha, K_s → sol_k)
    4. Fuzzy match (Levenshtein-like)

    Args:
        symbols: LaTeX symbols from the equation.
        variables: Code variable names.

    Returns:
        Tuple of (mappings, unmatched_symbols, unmatched_variables).
    """
    mappings: list[SymbolMapping] = []
    matched_symbols: set[str] = set()
    matched_variables: set[str] = set()

    var_lower = {v.lower(): v for v in variables}
    glossary = _load_symbol_glossary()

    for sym in symbols:
        norm = _normalize_symbol(sym)

        # Strategy 1: exact match
        if norm in var_lower:
            mappings.append(SymbolMapping(sym, var_lower[norm], 1.0, "exact"))
            matched_symbols.add(sym)
            matched_variables.add(var_lower[norm])
            continue

        # Strategy 2: normalized match (remove underscores, compare)
        norm_flat = norm.replace("_", "")
        for vl, vo in var_lower.items():
            if vo in matched_variables:
                continue
            if vl.replace("_", "") == norm_flat:
                mappings.append(SymbolMapping(sym, vo, 0.9, "normalized"))
                matched_symbols.add(sym)
                matched_variables.add(vo)
                break
        if sym in matched_symbols:
            continue

        # Strategy 3: Greek letter → code name
        if norm in _LATEX_TO_CODE:
            code_names = _LATEX_TO_CODE[norm]
            for cn in code_names:
                if cn in var_lower and var_lower[cn] not in matched_variables:
                    mappings.append(SymbolMapping(sym, var_lower[cn], 0.8, "glossary"))
                    matched_symbols.add(sym)
                    matched_variables.add(var_lower[cn])
                    break
        if sym in matched_symbols:
            continue

        # Strategy 3b: glossary-based
        if norm in glossary:
            for alias in glossary[norm]:
                if alias in var_lower and var_lower[alias] not in matched_variables:
                    mappings.append(
                        SymbolMapping(sym, var_lower[alias], 0.7, "glossary")
                    )
                    matched_symbols.add(sym)
                    matched_variables.add(var_lower[alias])
                    break
        if sym in matched_symbols:
            continue

        # Strategy 4: substring / prefix match
        for vl, vo in var_lower.items():
            if vo in matched_variables:
                continue
            if norm in vl or vl in norm:
                mappings.append(SymbolMapping(sym, vo, 0.5, "fuzzy"))
                matched_symbols.add(sym)
                matched_variables.add(vo)
                break

    unmatched_sym = [s for s in symbols if s not in matched_symbols]
    unmatched_var = [v for v in variables if v not in matched_variables]

    return mappings, unmatched_sym, unmatched_var


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------


def map_equation_to_code(
    equation_latex: str,
    source_path: Path,
    function_name: str | None = None,
    *,
    equation_number: str = "",
) -> EquationMapResult:
    """Map an equation's symbols to code variables.

    Args:
        equation_latex: LaTeX equation string.
        source_path: Path to source file.
        function_name: Optional function to scope variable extraction.
        equation_number: Equation number for display.

    Returns:
        EquationMapResult with proposed mappings and unmatched items.
    """
    symbols = extract_latex_symbols(equation_latex)
    variables = extract_code_variables(source_path, function_name)

    mappings, unmatched_sym, unmatched_var = match_symbols_to_variables(
        symbols, variables
    )

    return EquationMapResult(
        equation_latex=equation_latex,
        equation_number=equation_number,
        function_name=function_name or "(all)",
        file_path=str(source_path),
        mappings=mappings,
        unmatched_symbols=unmatched_sym,
        unmatched_variables=unmatched_var,
    )


def format_equation_map(result: EquationMapResult) -> str:
    """Format an equation map result as markdown.

    Args:
        result: EquationMapResult to format.

    Returns:
        Formatted markdown string.
    """
    eq_label = f"Eq. {result.equation_number}" if result.equation_number else "Equation"
    lines = [
        f"## {eq_label} → `{result.function_name}`\n",
        f"**Equation:** `{result.equation_latex}`",
        f"**File:** `{result.file_path}`\n",
    ]

    if result.mappings:
        lines.append("### Mappings\n")
        lines.append("| Symbol | Variable | Confidence | Method |")
        lines.append("|--------|----------|------------|--------|")
        for m in sorted(result.mappings, key=lambda x: -x.confidence):
            lines.append(
                f"| `{m.symbol}` | `{m.variable}` | {m.confidence:.0%} | {m.method} |"
            )

    if result.unmatched_symbols:
        lines.append("\n### Unmatched Symbols\n")
        for s in result.unmatched_symbols:
            lines.append(f"- `{s}` — no code variable found")

    if result.unmatched_variables:
        lines.append("\n### Unmatched Variables\n")
        for v in result.unmatched_variables:
            lines.append(f"- `{v}` — no equation symbol found")

    return "\n".join(lines)
