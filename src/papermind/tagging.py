"""Auto-tagging via TF-IDF keyword extraction. Zero external deps."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

# Common English stopwords + academic boilerplate
_STOPWORDS = frozenset(
    "a an the and or but in on at to for of is it by with from as be "
    "this that are was were been has have had do does did not no nor "
    "can could will would shall should may might must so than more "
    "also very much each such its our their these those which who whom "
    "what where when how why all any both few many some other another "
    "between through during before after above below up down out off "
    "over under again further then once here there about into onto "
    "et al fig table figure section results methods introduction "
    "discussion conclusion abstract references acknowledgments model "
    "data using used based study paper analysis however therefore "
    "approach proposed shown show shows presented present use "
    "different respectively according respectively given two three "
    "one first second new high low large small well within without".split()
)

_WORD_RE = re.compile(r"[a-z][a-z0-9_-]{2,}")


def _tokenize(text: str) -> list[str]:
    """Extract lowercase words, dropping stopwords and short tokens."""
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]


def extract_tags(
    text: str,
    corpus_texts: list[str],
    *,
    max_tags: int = 8,
    min_df: int = 1,
    max_df_ratio: float = 0.8,
) -> list[str]:
    """Extract keywords from text using TF-IDF against a corpus.

    Args:
        text: The document to tag.
        corpus_texts: All documents in the KB (including this one).
        max_tags: Maximum number of tags to return.
        min_df: Minimum document frequency (ignore ultra-rare terms).
        max_df_ratio: Maximum document frequency ratio (ignore terms
            appearing in >80% of documents — too common).

    Returns:
        List of keyword strings, sorted by TF-IDF score descending.
    """
    n_docs = len(corpus_texts)
    if n_docs == 0:
        return []

    # Build document frequency
    df: Counter[str] = Counter()
    for doc in corpus_texts:
        unique_terms = set(_tokenize(doc))
        for term in unique_terms:
            df[term] += 1

    # Compute TF for this document
    tokens = _tokenize(text)
    if not tokens:
        return []
    tf = Counter(tokens)
    max_tf = max(tf.values())

    # Score each term by TF-IDF
    scores: dict[str, float] = {}
    for term, count in tf.items():
        doc_freq = df.get(term, 0)
        if doc_freq < min_df:
            continue
        if doc_freq / n_docs > max_df_ratio:
            continue
        # Augmented TF to prevent bias toward long documents
        augmented_tf = 0.5 + 0.5 * (count / max_tf)
        idf = math.log(n_docs / (1 + doc_freq))
        scores[term] = augmented_tf * idf

    # Return top tags sorted by score
    ranked = sorted(scores, key=lambda t: scores[t], reverse=True)
    return ranked[:max_tags]


def tag_all_papers(kb_path: Path, max_tags: int = 8) -> dict[str, list[str]]:
    """Extract tags for all papers in the KB.

    Builds a corpus from all paper markdown files, then computes
    TF-IDF tags for each paper.

    Args:
        kb_path: Knowledge base root.
        max_tags: Maximum tags per paper.

    Returns:
        Dict mapping paper ID to list of tags.
    """
    import frontmatter as fm_lib

    papers_dir = kb_path / "papers"
    if not papers_dir.exists():
        return {}

    # Collect all paper texts and IDs
    paper_data: list[tuple[str, str, Path]] = []  # (id, text, path)
    for md_file in sorted(papers_dir.rglob("*.md")):
        if md_file.name == "catalog.md":
            continue
        try:
            post = fm_lib.load(md_file)
            if post.metadata.get("type") != "paper":
                continue
            paper_id = post.metadata.get("id", "")
            if not paper_id:
                continue
            paper_data.append((paper_id, post.content, md_file))
        except Exception:
            continue

    if not paper_data:
        return {}

    corpus = [text for _, text, _ in paper_data]
    result: dict[str, list[str]] = {}

    for paper_id, text, _ in paper_data:
        tags = extract_tags(text, corpus, max_tags=max_tags)
        result[paper_id] = tags

    return result
