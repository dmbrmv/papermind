"""Automated KB repair planning and application."""

from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

import frontmatter as fm_lib

from papermind.catalog.index import CatalogIndex

_DOI_URL_PREFIX = "https://doi.org/"


@dataclass
class RepairAction:
    """Single proposed metadata repair."""

    code: str
    path: str
    paper_id: str
    field: str
    current_value: str = ""
    proposed_value: str = ""
    confidence: str = "medium"
    reason: str = ""
    title: str = ""

    def to_dict(self) -> dict[str, str]:
        """Serialize to a dict."""
        return {k: str(v) for k, v in asdict(self).items() if v != ""}


def plan_kb_repairs(
    kb_path: Path,
    *,
    online: bool = True,
) -> list[RepairAction]:
    """Build a repair plan for historical paper metadata issues."""
    actions: list[RepairAction] = []
    catalog = CatalogIndex(kb_path)

    for entry in catalog.entries:
        if entry.type != "paper":
            continue

        full_path = kb_path / entry.path
        if not full_path.exists():
            continue

        try:
            post = fm_lib.load(full_path)
        except Exception:
            continue

        meta = dict(post.metadata)
        title = str(meta.get("title", "")).strip()
        doi = _normalize_doi(meta.get("doi", ""))
        year = _parse_year(meta.get("year"))
        paper_id = str(meta.get("id", entry.id)).strip() or entry.id

        remote = _fetch_work_by_doi(doi) if online and doi else None
        remote_title = str((remote or {}).get("title", "")).strip()
        remote_year = _parse_year((remote or {}).get("year"))
        remote_similarity = _title_similarity(title, remote_title) if remote_title else 0.0

        if year is None and remote_year and remote_similarity >= 0.75:
            actions.append(
                RepairAction(
                    code="set_year_from_doi",
                    path=entry.path,
                    paper_id=paper_id,
                    field="year",
                    proposed_value=str(remote_year),
                    confidence="high" if remote_similarity >= 0.9 else "medium",
                    reason=(
                        "OpenAlex DOI metadata matches local title and supplies a "
                        "publication year"
                    ),
                    title=title,
                )
            )

        if online and ((doi and remote_title and remote_similarity < 0.45) or not doi):
            candidate = _best_title_candidate(title, year)
            if candidate and candidate["doi"] and candidate["doi"] != doi:
                confidence = candidate["confidence"]
                if doi:
                    actions.append(
                        RepairAction(
                            code="replace_doi_from_title_match",
                            path=entry.path,
                            paper_id=paper_id,
                            field="doi",
                            current_value=doi,
                            proposed_value=candidate["doi"],
                            confidence=confidence,
                            reason=(
                                "Local title strongly matches OpenAlex search result "
                                "and current DOI points to a different work"
                            ),
                            title=title,
                        )
                    )
                else:
                    actions.append(
                        RepairAction(
                            code="set_doi_from_title_match",
                            path=entry.path,
                            paper_id=paper_id,
                            field="doi",
                            proposed_value=candidate["doi"],
                            confidence=confidence,
                            reason="Local title strongly matches OpenAlex search result",
                            title=title,
                        )
                    )

                candidate_year = _parse_year(candidate.get("year"))
                if year is None and candidate_year:
                    actions.append(
                        RepairAction(
                            code="set_year_from_title_match",
                            path=entry.path,
                            paper_id=paper_id,
                            field="year",
                            proposed_value=str(candidate_year),
                            confidence=confidence,
                            reason=(
                                "OpenAlex title match is strong and provides a "
                                "publication year"
                            ),
                            title=title,
                        )
                    )

    return _dedupe_actions(actions)


def apply_repair_actions(
    kb_path: Path,
    actions: list[RepairAction],
    *,
    min_confidence: str = "high",
) -> int:
    """Apply repair actions to paper frontmatter and rebuild catalog."""
    threshold = _confidence_rank(min_confidence)
    selected = [
        action
        for action in actions
        if _confidence_rank(action.confidence) <= threshold and action.path
    ]
    if not selected:
        return 0

    selected.sort(key=lambda action: (action.path, action.field, action.code))
    applied = 0
    current_path = ""
    post = None

    for action in selected:
        md_path = kb_path / action.path
        if not md_path.exists():
            continue

        if action.path != current_path:
            if post is not None:
                (kb_path / current_path).write_text(fm_lib.dumps(post), encoding="utf-8")
            post = fm_lib.load(md_path)
            current_path = action.path

        current_meta_value = post.metadata.get(action.field)
        normalized_current = str(current_meta_value) if current_meta_value is not None else ""
        if normalized_current and normalized_current == action.proposed_value:
            continue

        if action.field == "year":
            post.metadata[action.field] = int(action.proposed_value)
        else:
            post.metadata[action.field] = action.proposed_value
        applied += 1

    if post is not None and current_path:
        (kb_path / current_path).write_text(fm_lib.dumps(post), encoding="utf-8")

    if applied:
        CatalogIndex.rebuild(kb_path)
        from papermind.catalog.render import render_catalog_md

        catalog = CatalogIndex(kb_path)
        (kb_path / "catalog.md").write_text(
            render_catalog_md(catalog.entries),
            encoding="utf-8",
        )
    return applied


def summarize_actions(actions: list[RepairAction]) -> dict[str, int]:
    """Summarize actions by confidence."""
    summary = {"high": 0, "medium": 0, "low": 0, "total": len(actions)}
    for action in actions:
        summary[action.confidence] = summary.get(action.confidence, 0) + 1
    return summary


async def _fetch_openalex_work_by_doi(doi: str, timeout: float = 10.0) -> dict | None:
    """Fetch title/year metadata for a DOI from OpenAlex."""
    import httpx

    if not doi:
        return None

    url = f"https://api.openalex.org/works/doi:{doi}"
    params = {"mailto": "papermind@users.noreply", "select": "title,publication_year,doi"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
    except Exception:
        return None

    return {
        "title": str(data.get("title", "")).strip(),
        "year": data.get("publication_year"),
        "doi": _normalize_doi(data.get("doi", "")),
    }


async def _search_openalex_by_title(
    title: str,
    *,
    per_page: int = 5,
    timeout: float = 10.0,
) -> list[dict]:
    """Search OpenAlex by title and return compact work metadata."""
    import httpx

    if not title.strip():
        return []

    params = {
        "search": title,
        "per-page": per_page,
        "mailto": "papermind@users.noreply",
        "select": "title,publication_year,doi",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get("https://api.openalex.org/works", params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception:
        return []

    results = []
    for item in data.get("results", []):
        results.append(
            {
                "title": str(item.get("title", "")).strip(),
                "year": item.get("publication_year"),
                "doi": _normalize_doi(item.get("doi", "")),
            }
        )
    return results


def _fetch_work_by_doi(doi: str) -> dict | None:
    """Sync wrapper around DOI metadata lookup."""
    return asyncio.run(_fetch_openalex_work_by_doi(doi))


def _search_title(title: str) -> list[dict]:
    """Sync wrapper around title search."""
    return asyncio.run(_search_openalex_by_title(title))


def _best_title_candidate(title: str, year: int | None) -> dict | None:
    """Choose the strongest OpenAlex title match, if unambiguous."""
    candidates = []
    for item in _search_title(title):
        candidate_title = str(item.get("title", "")).strip()
        candidate_year = _parse_year(item.get("year"))
        similarity = _title_similarity(title, candidate_title)
        if similarity < 0.88:
            continue
        if year is not None and candidate_year is not None and abs(candidate_year - year) > 1:
            continue
        item = dict(item)
        item["similarity"] = similarity
        candidates.append(item)

    if not candidates:
        return None

    candidates.sort(key=lambda item: item["similarity"], reverse=True)
    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    if second and (best["similarity"] - second["similarity"]) < 0.03:
        return None

    best["confidence"] = "high" if best["similarity"] >= 0.94 else "medium"
    return best


def _normalize_doi(value: object) -> str:
    """Normalize DOI strings from local and remote metadata."""
    doi = str(value or "").strip()
    if not doi:
        return ""
    if doi.lower().startswith(_DOI_URL_PREFIX):
        doi = doi[len(_DOI_URL_PREFIX) :]
    return doi.rstrip(".,;) ")


def _normalize_title(title: str) -> str:
    """Normalize titles for approximate comparison."""
    text = title.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _title_similarity(left: str, right: str) -> float:
    """Title similarity in the range [0, 1]."""
    if not left.strip() or not right.strip():
        return 0.0
    return SequenceMatcher(None, _normalize_title(left), _normalize_title(right)).ratio()


def _parse_year(value: object) -> int | None:
    """Parse year values from local or remote metadata."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe_actions(actions: list[RepairAction]) -> list[RepairAction]:
    """Drop duplicate actions for the same path/field/value tuple."""
    unique: dict[tuple[str, str, str], RepairAction] = {}
    for action in actions:
        key = (action.path, action.field, action.proposed_value)
        existing = unique.get(key)
        if existing is None or _confidence_rank(action.confidence) < _confidence_rank(
            existing.confidence
        ):
            unique[key] = action
    return sorted(unique.values(), key=lambda item: (item.path, item.field, item.code))


def _confidence_rank(confidence: str) -> int:
    """Sort confidences from strongest to weakest."""
    return {"high": 0, "medium": 1, "low": 2}.get(confidence, 3)
