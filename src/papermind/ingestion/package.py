"""Package ingestion — griffe API extraction + markdown rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import griffe
from jinja2 import Template

from papermind.catalog.index import CatalogEntry, CatalogIndex
from papermind.catalog.render import render_catalog_md
from papermind.config import PaperMindConfig
from papermind.ingestion.common import build_frontmatter


@dataclass
class ModuleAPI:
    """Extracted API for one module."""

    name: str
    docstring: str = ""
    functions: list[dict] = field(default_factory=list)  # {name, signature, docstring}
    classes: list[dict] = field(default_factory=list)  # {name, docstring, methods}


@dataclass
class PackageAPI:
    """Extracted API for a whole package."""

    modules: list[ModuleAPI] = field(default_factory=list)


def _extract_module(member: object) -> ModuleAPI:
    """Extract API from a single griffe Module object.

    Args:
        member: A griffe Module object.

    Returns:
        Populated ModuleAPI dataclass.
    """
    mod = ModuleAPI(
        name=member.path,  # type: ignore[attr-defined]
        docstring=member.docstring.value if member.docstring else "",  # type: ignore[attr-defined]
    )
    sub_members: dict = getattr(member, "members", {})
    for sub_name, sub_member in sub_members.items():
        kind = getattr(sub_member, "kind", None)
        if kind is None:
            continue
        kind_name: str = kind.name
        if kind_name == "FUNCTION":
            params = ", ".join(p.name for p in getattr(sub_member, "parameters", []))
            mod.functions.append(
                {
                    "name": sub_name,
                    "signature": f"{sub_name}({params})",
                    "docstring": (
                        sub_member.docstring.value if sub_member.docstring else ""
                    ),
                }
            )
        elif kind_name == "CLASS":
            methods = [
                method_name
                for method_name, method in getattr(sub_member, "members", {}).items()
                if getattr(getattr(method, "kind", None), "name", "") == "FUNCTION"
            ]
            mod.classes.append(
                {
                    "name": sub_name,
                    "docstring": (
                        sub_member.docstring.value if sub_member.docstring else ""
                    ),
                    "methods": methods,
                }
            )
    return mod


def extract_api(package_name: str) -> PackageAPI:
    """Extract API structure from an installed Python package.

    Loads the package with griffe (static analysis), then walks all
    top-level module members to collect functions, classes, and
    docstrings.

    Args:
        package_name: Import name of the installed package (e.g. "papermind").

    Returns:
        PackageAPI containing one ModuleAPI per top-level module member.

    Raises:
        griffe.LoadingError: If the package cannot be found or loaded.
    """
    pkg = griffe.load(package_name)
    result = PackageAPI()

    for member in pkg.members.values():
        kind = getattr(member, "kind", None)
        if kind is None:
            continue
        # Only recurse into modules; skip aliases, attributes, etc.
        if kind.name == "MODULE":
            result.modules.append(_extract_module(member))

    return result


_API_TEMPLATE_SRC = """\
# {{ package_name }} API Reference

{% for mod in api.modules %}
## {{ mod.name }}

{% if mod.docstring %}{{ mod.docstring }}

{% endif %}
{% for func in mod.functions %}
### `{{ func.signature }}`

{% if func.docstring %}{{ func.docstring }}

{% endif %}
{% endfor %}
{% for cls in mod.classes %}
### class `{{ cls.name }}`

{% if cls.docstring %}{{ cls.docstring }}

{% endif %}
{% if cls.methods %}**Methods:** {{ cls.methods | join(', ') }}

{% endif %}
{% endfor %}
{% endfor %}
"""

API_TEMPLATE = Template(_API_TEMPLATE_SRC)


def render_api_markdown(api: PackageAPI, package_name: str) -> str:
    """Render PackageAPI into a markdown string.

    Args:
        api: Extracted package API structure.
        package_name: Package name used as the document title.

    Returns:
        Rendered markdown string.
    """
    return API_TEMPLATE.render(api=api, package_name=package_name)


def ingest_package(
    package_name: str,
    kb_path: Path,
    config: PaperMindConfig,
    *,
    docs_url: str = "",
    no_reindex: bool = False,
) -> CatalogEntry:
    """Full package ingestion pipeline.

    Extracts the package API via griffe, optionally fetches web docs,
    writes files to packages/<name>/, updates catalog.json, and
    regenerates catalog.md.

    Args:
        package_name: Python package name (must be importable).
        kb_path: Knowledge base root.
        config: PaperMind configuration.
        docs_url: Optional documentation URL to crawl.
        no_reindex: If True, skip qmd reindex.

    Returns:
        CatalogEntry for the ingested package.
    """
    import frontmatter as fm_lib

    # 1. Extract API via griffe
    api = extract_api(package_name)
    api_md = render_api_markdown(api, package_name)

    # 2. Optionally fetch web docs
    docs_md = ""
    if docs_url and not config.offline_only:
        docs_md = _fetch_docs(docs_url, config)
    elif not docs_url and not config.offline_only:
        # Try to resolve docs URL from PyPI
        resolved_url = _resolve_docs_url(package_name)
        if resolved_url:
            docs_url = resolved_url
            docs_md = _fetch_docs(resolved_url, config)

    # 3. Write files (clean old files on re-ingestion)
    pkg_dir = kb_path / "packages" / package_name
    if pkg_dir.exists():
        import shutil

        shutil.rmtree(pkg_dir)
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "api.md").write_text(api_md)
    files = ["api.md"]

    if docs_md:
        (pkg_dir / "docs.md").write_text(docs_md)
        files.append("docs.md")

    # _index.md with frontmatter
    fm = build_frontmatter(
        type="package",
        id=f"package-{package_name}",
        name=package_name,
        source_url=docs_url,
    )

    index_content = (
        f"# {package_name}\n\nPython package API reference and documentation.\n"
    )
    if docs_url:
        index_content += f"\n**Documentation:** {docs_url}\n"
    index_content += f"\n**Files:** {', '.join(files)}\n"

    post = fm_lib.Post(index_content)
    post.metadata = fm
    (pkg_dir / "_index.md").write_text(fm_lib.dumps(post))

    # 4. Update catalog
    catalog = CatalogIndex(kb_path)
    entry_id = f"package-{package_name}"

    existing = catalog.get(entry_id)
    if existing:
        catalog.remove(entry_id)

    entry = CatalogEntry(
        id=entry_id,
        type="package",
        title=package_name,
        path=f"packages/{package_name}/_index.md",
        source_url=docs_url,
        files=files,
        added=existing.added if existing else fm["added"],
        updated=fm["added"] if existing else "",
    )
    catalog.add(entry)

    # 5. Regenerate catalog.md
    (kb_path / "catalog.md").write_text(render_catalog_md(catalog.entries))

    return entry


def _resolve_docs_url(package_name: str) -> str:
    """Try to find docs URL from PyPI metadata.

    Args:
        package_name: PyPI package name.

    Returns:
        Documentation URL if found, otherwise empty string.
    """
    import httpx

    try:
        resp = httpx.get(f"https://pypi.org/pypi/{package_name}/json", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            urls = data.get("info", {}).get("project_urls") or {}
            for key in ["Documentation", "Docs", "documentation", "docs", "Homepage"]:
                if key in urls:
                    return urls[key]  # type: ignore[no-any-return]
    except Exception:
        pass
    return ""


def _fetch_docs(url: str, config: PaperMindConfig) -> str:
    """Fetch docs from URL. Try Firecrawl if key available, else basic httpx.

    Args:
        url: URL to fetch documentation from.
        config: PaperMind configuration (used to check for Firecrawl key).

    Returns:
        Fetched content as a markdown string, or empty string on failure.
    """
    if config.firecrawl_key:
        return _fetch_via_firecrawl(url, config.firecrawl_key)
    return _fetch_basic(url)


def _fetch_via_firecrawl(url: str, api_key: str) -> str:
    """Fetch page via Firecrawl API.

    Args:
        url: URL to scrape.
        api_key: Firecrawl API key.

    Returns:
        Markdown content from Firecrawl, or empty string on failure.
    """
    import httpx

    try:
        resp = httpx.post(
            "https://api.firecrawl.dev/v1/scrape",
            json={"url": url, "formats": ["markdown"]},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("markdown", "")  # type: ignore[no-any-return]
    except Exception:
        pass
    return ""


def _fetch_basic(url: str) -> str:
    """Basic HTTP fetch — returns raw response text up to 50 KB.

    Args:
        url: URL to fetch.

    Returns:
        Response text (up to 50 000 characters), or empty string on failure.
    """
    import httpx

    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text[:50000]
    except Exception:
        pass
    return ""
