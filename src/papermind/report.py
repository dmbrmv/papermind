"""Collection reports — structured topic overviews from KB content."""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

import frontmatter as fm_lib

logger = logging.getLogger(__name__)


def generate_report(kb_path: Path, topic: str) -> str:
    """Generate a structured overview report for a KB topic.

    Scans all papers in the topic directory, extracts metadata (title, year,
    DOI, abstract, tags, equations), and produces a markdown report with:
    - Paper inventory (ranked by year, descending)
    - Method/keyword taxonomy from tags
    - Equations catalog (if any papers have extracted equations)
    - Coverage gaps (years, missing abstracts, missing DOIs)

    Args:
        kb_path: Knowledge base root directory.
        topic: Topic name (must match a subdirectory under papers/).

    Returns:
        Markdown report string.

    Raises:
        FileNotFoundError: If the topic directory doesn't exist.
    """
    topic_dir = kb_path / "papers" / topic
    if not topic_dir.is_dir():
        raise FileNotFoundError(f"Topic directory not found: {topic_dir}")

    papers = _load_topic_papers(topic_dir, kb_path)
    if not papers:
        return f"# {topic}\n\nNo papers found in this topic.\n"

    sections = [
        f"# Report: {topic}",
        f"\n{len(papers)} paper(s) in this topic.\n",
        _section_inventory(papers),
        _section_taxonomy(papers),
        _section_equations(papers, topic_dir),
        _section_coverage(papers),
    ]

    return "\n".join(s for s in sections if s)


def _load_topic_papers(topic_dir: Path, kb_path: Path) -> list[dict]:
    """Load metadata from all papers in a topic directory."""
    papers = []
    for paper_md in sorted(topic_dir.rglob("paper.md")):
        try:
            post = fm_lib.load(paper_md)
            meta = dict(post.metadata)
            meta["_path"] = str(paper_md.relative_to(kb_path))
            meta["_content_length"] = len(post.content)
            papers.append(meta)
        except Exception:
            logger.debug("Failed to load %s", paper_md)
    return papers


def _section_inventory(papers: list[dict]) -> str:
    """Paper inventory sorted by year (newest first)."""
    lines = ["## Papers\n"]

    # Sort by year descending, then title
    sorted_papers = sorted(
        papers,
        key=lambda p: (-(p.get("year") or 0), p.get("title", "")),
    )

    for p in sorted_papers:
        year = p.get("year", "?")
        title = p.get("title", "Untitled")
        doi = p.get("doi", "")
        path = p.get("_path", "")

        line = f"- **{title}** ({year})"
        if doi:
            line += f" — DOI: {doi}"
        if path:
            line += f"\n  `{path}`"
        lines.append(line)

    return "\n".join(lines)


def _section_taxonomy(papers: list[dict]) -> str:
    """Method / keyword taxonomy from tags."""
    tag_counter: Counter[str] = Counter()
    for p in papers:
        tags = p.get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                tag_counter[tag] += 1

    if not tag_counter:
        return ""

    lines = ["\n## Keywords\n"]
    for tag, count in tag_counter.most_common(30):
        lines.append(f"- {tag} ({count})")

    return "\n".join(lines)


def _section_equations(papers: list[dict], topic_dir: Path) -> str:
    """Equations catalog — scan for extracted equations in paper content."""
    import re

    eq_papers = []
    for paper_md in sorted(topic_dir.rglob("paper.md")):
        try:
            content = paper_md.read_text()
        except Exception:
            continue

        # Find LaTeX-style equations ($$...$$) or inline ($...$)
        block_eqs = re.findall(r"\$\$(.+?)\$\$", content, re.DOTALL)
        if block_eqs:
            post = fm_lib.load(paper_md)
            title = post.metadata.get("title", paper_md.parent.name)
            eq_papers.append((title, len(block_eqs)))

    if not eq_papers:
        return ""

    lines = ["\n## Equations\n"]
    for title, count in sorted(eq_papers, key=lambda x: -x[1]):
        lines.append(f"- **{title}**: {count} equation(s)")

    return "\n".join(lines)


def _section_coverage(papers: list[dict]) -> str:
    """Coverage analysis — identify gaps."""
    lines = ["\n## Coverage\n"]

    years = [p["year"] for p in papers if p.get("year")]
    if years:
        lines.append(f"- **Year range:** {min(years)} – {max(years)}")
    else:
        lines.append("- **Year range:** unknown (no years in metadata)")

    no_abstract = sum(1 for p in papers if not p.get("abstract"))
    no_doi = sum(1 for p in papers if not p.get("doi"))

    lines.append(f"- **Missing abstracts:** {no_abstract}/{len(papers)}")
    lines.append(f"- **Missing DOIs:** {no_doi}/{len(papers)}")

    return "\n".join(lines)
