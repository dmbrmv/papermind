"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SearchParams(BaseModel):
    """Common search query parameters."""

    q: str
    scope: str = ""
    topic: str = ""
    year_from: int | None = None
    limit: int = 20


class ScanResult(BaseModel):
    """A single scan result."""

    rank: int
    score: float
    title: str
    path: str


class SummaryResult(BaseModel):
    """A single summary result with metadata."""

    title: str
    path: str
    doi: str = ""
    year: int | None = None
    topic: str = ""
    abstract: str = ""
    snippet: str = ""
    citations: str = ""


class SearchResponse(BaseModel):
    """Response for scan/summary endpoints."""

    query: str
    count: int
    results: list[ScanResult] | list[SummaryResult]


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class PaperResponse(BaseModel):
    """Paper entry from the catalog."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    path: str
    title: str = ""
    topic: str = ""
    doi: str = ""
    tags: list[str] = []
    added: str = ""


class CatalogStatsResponse(BaseModel):
    """Knowledge base statistics."""

    total: int
    papers: int
    packages: int
    codebases: int
    topics: dict[str, int]


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class SessionCreateRequest(BaseModel):
    """Request to create a session."""

    name: str


class SessionAddRequest(BaseModel):
    """Request to add an entry to a session."""

    content: str
    agent: str = "api"
    tags: list[str] = []


class SessionEntryResponse(BaseModel):
    """A single session entry."""

    agent: str
    content: str
    tags: list[str]
    timestamp: str


class SessionResponse(BaseModel):
    """Full session with entries."""

    id: str
    name: str
    created: str
    closed: bool
    entries: list[SessionEntryResponse]


class SessionListItem(BaseModel):
    """Session metadata for list endpoint."""

    id: str
    name: str
    created: str
    closed: bool
    entry_count: int


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class ExplainRequest(BaseModel):
    """Request to explain a concept."""

    concept: str


class ExplainResponse(BaseModel):
    """Explanation of a concept/parameter."""

    name: str
    definition: str
    range: list[float] | None = None
    unit: str | None = None
    related: list[str] = []
    ref: str = ""
    source: str = ""


class ProvenanceRequest(BaseModel):
    """Request to extract provenance from a file."""

    file_path: str


class CodeRefResponse(BaseModel):
    """A single code-to-paper reference."""

    file: str
    line: int
    identifier: str
    identifier_type: str
    location: str


class EquationMapRequest(BaseModel):
    """Request to map equation symbols to code."""

    equation_latex: str
    file_path: str
    function_name: str | None = None


class SymbolMappingResponse(BaseModel):
    """A proposed symbol→variable mapping."""

    symbol: str
    variable: str
    confidence: float
    method: str


class EquationMapResponse(BaseModel):
    """Equation-to-code mapping result."""

    equation_latex: str
    function_name: str
    mappings: list[SymbolMappingResponse]
    unmatched_symbols: list[str]
    unmatched_variables: list[str]


class VerifyRequest(BaseModel):
    """Request to verify code against a paper equation."""

    paper_id: str
    equation_number: str
    file_path: str
    function_name: str | None = None


class VerifyResponse(BaseModel):
    """Verification result."""

    paper_id: str
    paper_title: str
    equation_number: str
    coverage: float
    avg_confidence: float
    verdict: str
    mappings: list[dict]
    unmatched_symbols: list[str]
    provenance_refs: list[dict]


class ResolveRefsRequest(BaseModel):
    """Request to resolve kb: references."""

    text: str


class ResolvedRefResponse(BaseModel):
    """A resolved kb: reference."""

    raw: str
    identifier: str
    found: bool
    title: str = ""
    path: str = ""
    topic: str = ""
    line: int = 0


class WatchFileRequest(BaseModel):
    """Request to watch a source file."""

    file_path: str
    limit: int = 5


class ProfileRequest(BaseModel):
    """Request to generate a project profile."""

    codebase_path: str


class ProfileResponse(BaseModel):
    """Project profile summary."""

    name: str
    languages: list[str]
    file_count: int
    function_count: int
    class_count: int
    linked_papers: list[str]
    key_topics: list[str]
    readme_excerpt: str = ""


# ---------------------------------------------------------------------------
# API Diff
# ---------------------------------------------------------------------------


class APIDiffResponse(BaseModel):
    """API version diff result."""

    old_name: str
    new_name: str
    old_count: int
    new_count: int
    added: list[dict]
    removed: list[dict]
    changed: list[dict]


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
