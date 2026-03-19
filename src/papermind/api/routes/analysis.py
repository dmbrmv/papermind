"""Analysis endpoints — explain, provenance, equation-map, verify, etc."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from papermind.api.deps import get_kb_path, validate_file_path
from papermind.api.schemas import (
    EquationMapRequest,
    ExplainRequest,
    ProfileRequest,
    ProvenanceRequest,
    ResolveRefsRequest,
    VerifyRequest,
    WatchFileRequest,
)

router = APIRouter()


@router.post("/analysis/explain")
async def explain_concept(
    body: ExplainRequest,
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Explain a hydrological parameter or concept."""
    from papermind.explain import explain

    result = explain(body.concept, kb_path=kb_path)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"No explanation found for '{body.concept}'"
        )

    return {
        "name": result.name,
        "definition": result.definition,
        "range": result.range,
        "unit": result.unit,
        "related": result.related,
        "ref": result.ref,
        "source": result.source,
    }


@router.post("/analysis/provenance")
async def extract_provenance(
    body: ProvenanceRequest,
    request: Request,
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Extract # REF: annotations from a source file."""
    from papermind.provenance import extract_provenance as _extract

    file_path = validate_file_path(body.file_path, request)
    refs = await asyncio.to_thread(_extract, file_path)

    return {
        "file": str(file_path),
        "count": len(refs),
        "refs": [
            {
                "line": r.line,
                "identifier": r.identifier,
                "identifier_type": r.identifier_type,
                "location": r.location,
            }
            for r in refs
        ],
    }


@router.post("/analysis/equation-map")
async def equation_map(
    body: EquationMapRequest,
    request: Request,
) -> dict:
    """Map equation symbols to code variables."""
    from papermind.equation_map import map_equation_to_code

    file_path = validate_file_path(body.file_path, request)
    result = await asyncio.to_thread(
        map_equation_to_code, body.equation_latex, file_path, body.function_name
    )

    return {
        "equation_latex": result.equation_latex,
        "function_name": result.function_name,
        "mappings": [
            {
                "symbol": m.symbol,
                "variable": m.variable,
                "confidence": m.confidence,
                "method": m.method,
            }
            for m in result.mappings
        ],
        "unmatched_symbols": result.unmatched_symbols,
        "unmatched_variables": result.unmatched_variables,
    }


@router.post("/analysis/verify")
async def verify_implementation(
    body: VerifyRequest,
    request: Request,
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Verify code implements a paper equation."""
    from papermind.verify import verify_implementation as _verify

    file_path = validate_file_path(body.file_path, request)
    result = await asyncio.to_thread(
        _verify,
        body.paper_id,
        body.equation_number,
        file_path,
        body.function_name,
        kb_path,
    )

    return {
        "paper_id": result.paper_id,
        "paper_title": result.paper_title,
        "equation_number": result.equation_number,
        "coverage": result.coverage,
        "avg_confidence": result.avg_confidence,
        "verdict": result.verdict,
        "mappings": result.mappings,
        "unmatched_symbols": result.unmatched_symbols,
        "provenance_refs": result.provenance_refs,
    }


@router.post("/analysis/watch-file")
async def watch_file(
    body: WatchFileRequest,
    request: Request,
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Surface relevant KB entries for a source file."""
    from papermind.watch import watch_file as _watch

    file_path = validate_file_path(body.file_path, request)
    results = await asyncio.to_thread(_watch, file_path, kb_path, limit=body.limit)

    return {
        "file": str(file_path),
        "count": len(results),
        "results": [
            {"title": r.title, "path": r.path, "score": r.score, "snippet": r.snippet}
            for r in results
        ],
    }


@router.post("/analysis/project-profile")
async def project_profile(
    body: ProfileRequest,
    request: Request,
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Generate a project profile from codebase analysis."""
    from papermind.profile import generate_profile

    codebase_path = validate_file_path(body.codebase_path, request)
    if not codebase_path.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    profile = await asyncio.to_thread(generate_profile, codebase_path, kb_path)

    return {
        "name": profile.name,
        "languages": profile.languages,
        "file_count": profile.file_count,
        "function_count": profile.function_count,
        "class_count": profile.class_count,
        "linked_papers": profile.linked_papers,
        "key_topics": profile.key_topics,
        "readme_excerpt": profile.readme_excerpt,
    }


@router.post("/analysis/resolve-refs")
async def resolve_refs(
    body: ResolveRefsRequest,
    kb_path: Path = Depends(get_kb_path),
) -> dict:
    """Resolve kb: references in markdown text."""
    from papermind.memory import extract_kb_refs
    from papermind.memory import resolve_refs as _resolve

    refs = extract_kb_refs(body.text)
    if not refs:
        return {"count": 0, "refs": []}

    resolved = _resolve(refs, kb_path)
    return {
        "count": len(resolved),
        "refs": [
            {
                "raw": r.ref.raw,
                "identifier": r.ref.identifier,
                "line": r.ref.line,
                "found": r.found,
                "title": r.title,
                "path": r.path,
                "topic": r.topic,
            }
            for r in resolved
        ],
    }
