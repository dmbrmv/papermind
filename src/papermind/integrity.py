"""Knowledge-base integrity checks for paper metadata and catalog state."""

from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

import frontmatter as fm_lib

from papermind.catalog.index import CatalogIndex

_DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$")


@dataclass
class IntegrityFinding:
    """Single integrity finding."""

    severity: str
    code: str
    message: str
    path: str = ""
    paper_id: str = ""
    title: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        """Serialize to a dict."""
        return {k: str(v) for k, v in asdict(self).items() if v != ""}


def validate_paper_metadata(
    metadata: dict,
    *,
    path: str = "",
    require_id: bool = True,
) -> list[IntegrityFinding]:
    """Validate paper frontmatter without checking catalog state."""
    findings: list[IntegrityFinding] = []

    paper_id = str(metadata.get("id", "")).strip()
    title = str(metadata.get("title", "")).strip()
    topic = str(metadata.get("topic", "")).strip()
    entry_type = str(metadata.get("type", "")).strip()
    doi = str(metadata.get("doi", "")).strip()
    year = metadata.get("year")
    cites = metadata.get("cites")
    cited_by = metadata.get("cited_by")

    def add(severity: str, code: str, message: str, detail: str = "") -> None:
        findings.append(
            IntegrityFinding(
                severity=severity,
                code=code,
                message=message,
                detail=detail,
                path=path,
                paper_id=paper_id,
                title=title,
            )
        )

    if entry_type != "paper":
        add("error", "invalid_type", "Paper entry must declare type=paper")
    if require_id and not paper_id:
        add("error", "missing_id", "Paper entry is missing required field 'id'")
    if not title:
        add("error", "missing_title", "Paper entry is missing required field 'title'")
    if not topic:
        add("error", "missing_topic", "Paper entry is missing required field 'topic'")

    if doi and not _DOI_RE.match(doi):
        add("error", "invalid_doi", "DOI does not match expected format", detail=doi)

    if year not in (None, ""):
        try:
            year_num = int(year)
            if year_num < 1900 or year_num > 2100:
                add("error", "invalid_year", "Year is outside allowed range", detail=str(year))
        except (TypeError, ValueError):
            add("error", "invalid_year", "Year is not an integer", detail=str(year))
    else:
        add("info", "missing_year", "Paper entry has no publication year")

    if cites is not None and not (
        isinstance(cites, list) and all(isinstance(item, str) for item in cites)
    ):
        add("error", "invalid_cites", "Field 'cites' must be a list of DOI strings")
    if cited_by is not None and not (
        isinstance(cited_by, list) and all(isinstance(item, str) for item in cited_by)
    ):
        add(
            "error",
            "invalid_cited_by",
            "Field 'cited_by' must be a list of DOI strings",
        )

    return findings


async def _fetch_openalex_title(doi: str, timeout: float = 10.0) -> str | None:
    """Fetch a title for a DOI from OpenAlex."""
    import httpx

    if not doi:
        return None

    url = f"https://api.openalex.org/works/doi:{doi}"
    params = {"mailto": "papermind@users.noreply", "select": "title"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            title = data.get("title")
            return str(title).strip() if title else None
    except Exception:
        return None


def _normalize_title(title: str) -> str:
    """Normalize titles for approximate comparison."""
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _title_similarity(left: str, right: str) -> float:
    """Title similarity in the range [0, 1]."""
    return SequenceMatcher(None, _normalize_title(left), _normalize_title(right)).ratio()


def scan_kb_integrity(
    kb_path: Path,
    *,
    online: bool = False,
) -> list[IntegrityFinding]:
    """Scan KB paper entries and catalog state for integrity problems."""
    findings: list[IntegrityFinding] = []
    catalog = CatalogIndex(kb_path)
    paper_entries = [entry for entry in catalog.entries if entry.type == "paper"]

    id_counts: dict[str, int] = {}
    doi_counts: dict[str, int] = {}
    path_to_entry: dict[str, object] = {}
    doi_checks: list[tuple[str, str, str, str]] = []

    for entry in paper_entries:
        id_counts[entry.id] = id_counts.get(entry.id, 0) + 1
        if entry.doi:
            doi_counts[entry.doi] = doi_counts.get(entry.doi, 0) + 1
        path_to_entry[entry.path] = entry

    for paper_id, count in id_counts.items():
        if count > 1:
            findings.append(
                IntegrityFinding(
                    severity="error",
                    code="duplicate_id",
                    message=f"Paper ID appears {count} times in catalog",
                    paper_id=paper_id,
                )
            )

    for doi, count in doi_counts.items():
        if count > 1:
            findings.append(
                IntegrityFinding(
                    severity="error",
                    code="duplicate_doi",
                    message=f"DOI appears {count} times in catalog",
                    detail=doi,
                )
            )

    for entry in paper_entries:
        full_path = kb_path / entry.path
        if not full_path.exists():
            findings.append(
                IntegrityFinding(
                    severity="error",
                    code="missing_file",
                    message="Catalog paper path does not exist on disk",
                    path=entry.path,
                    paper_id=entry.id,
                    title=entry.title,
                )
            )
            continue

        try:
            post = fm_lib.load(full_path)
        except Exception as exc:
            findings.append(
                IntegrityFinding(
                    severity="error",
                    code="malformed_frontmatter",
                    message="Paper file frontmatter could not be parsed",
                    path=entry.path,
                    paper_id=entry.id,
                    title=entry.title,
                    detail=str(exc),
                )
            )
            continue

        meta = dict(post.metadata)
        findings.extend(validate_paper_metadata(meta, path=entry.path))

        file_id = str(meta.get("id", "")).strip()
        if file_id and file_id != entry.id:
            findings.append(
                IntegrityFinding(
                    severity="error",
                    code="catalog_id_mismatch",
                    message="Catalog ID does not match frontmatter ID",
                    path=entry.path,
                    paper_id=entry.id,
                    title=entry.title,
                    detail=file_id,
                )
            )

        file_doi = str(meta.get("doi", "")).strip()
        file_title = str(meta.get("title", "")).strip()
        if file_doi and file_title:
            doi_checks.append((entry.path, file_id or entry.id, file_title, file_doi))

    for md_file in sorted((kb_path / "papers").rglob("*.md")) if (kb_path / "papers").exists() else []:
        rel_path = str(md_file.relative_to(kb_path))
        if rel_path in path_to_entry:
            continue
        try:
            post = fm_lib.load(md_file)
        except Exception as exc:
            findings.append(
                IntegrityFinding(
                    severity="error",
                    code="malformed_frontmatter",
                    message="Paper file frontmatter could not be parsed",
                    path=rel_path,
                    detail=str(exc),
                )
            )
            continue

        meta = dict(post.metadata)
        if not meta:
            continue
        if meta.get("type") == "paper" or md_file.name == "paper.md":
            findings.extend(validate_paper_metadata(meta, path=rel_path))
            findings.append(
                IntegrityFinding(
                    severity="warning",
                    code="unindexed_paper_file",
                    message="Paper-like file exists under papers/ but is not in catalog",
                    path=rel_path,
                    paper_id=str(meta.get("id", "")).strip(),
                    title=str(meta.get("title", "")).strip(),
                )
            )

    if online and doi_checks:
        for path, paper_id, title, doi in doi_checks:
            remote_title = asyncio.run(_fetch_openalex_title(doi))
            if not remote_title:
                continue
            similarity = _title_similarity(title, remote_title)
            if similarity < 0.45:
                findings.append(
                    IntegrityFinding(
                        severity="warning",
                        code="doi_title_mismatch",
                        message="DOI resolves to a title that does not match local metadata",
                        path=path,
                        paper_id=paper_id,
                        title=title,
                        detail=f"doi={doi}; remote_title={remote_title}",
                    )
                )

    findings.sort(key=lambda item: (_severity_rank(item.severity), item.code, item.path, item.paper_id))
    return findings


def summarize_findings(findings: list[IntegrityFinding]) -> dict[str, int]:
    """Summarize findings by severity."""
    summary = {"error": 0, "warning": 0, "info": 0}
    for finding in findings:
        summary[finding.severity] = summary.get(finding.severity, 0) + 1
    summary["total"] = len(findings)
    return summary


def max_severity(findings: list[IntegrityFinding]) -> str:
    """Return the maximum severity present in findings."""
    if any(f.severity == "error" for f in findings):
        return "error"
    if any(f.severity == "warning" for f in findings):
        return "warning"
    if any(f.severity == "info" for f in findings):
        return "info"
    return "none"


def should_fail(findings: list[IntegrityFinding], fail_on: str) -> bool:
    """Decide whether a given finding set should fail."""
    highest = max_severity(findings)
    if fail_on == "never":
        return False
    if fail_on == "warning":
        return highest in {"error", "warning"}
    return highest == "error"


def _severity_rank(severity: str) -> int:
    """Sort severities from highest to lowest importance."""
    return {"error": 0, "warning": 1, "info": 2}.get(severity, 3)
