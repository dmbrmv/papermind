"""Render CodebaseMap into markdown files for the knowledge base."""

from __future__ import annotations

from pathlib import Path

from hydrofound.ingestion.codebase import CodebaseMap


def render_codebase(cb: CodebaseMap, output_dir: Path) -> list[Path]:
    """Render a codebase map into markdown files.

    Args:
        cb: Parsed codebase map from walk_codebase().
        output_dir: Directory to write markdown files.

    Returns:
        List of created file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    # _index.md — overview with frontmatter
    index_path = output_dir / "_index.md"
    langs = ", ".join(sorted(cb.languages))
    index_content = (
        f"---\ntype: codebase\nname: {cb.name}\nlanguages: [{langs}]\n---\n\n"
        f"# {cb.name}\n\n"
        f"**Languages:** {langs}\n"
        f"**Files:** {len(cb.file_tree)}\n\n"
    )
    if cb.readme_content:
        index_content += f"## README\n\n{cb.readme_content}\n"
    index_path.write_text(index_content)
    created.append(index_path)

    # structure.md — file tree
    structure_path = output_dir / "structure.md"
    tree_lines = [f"# {cb.name} — File Structure\n"]
    for f in sorted(cb.file_tree):
        tree_lines.append(f"- `{f}`")
    structure_path.write_text("\n".join(tree_lines) + "\n")
    created.append(structure_path)

    # signatures.md — all extracted signatures
    sigs_path = output_dir / "signatures.md"
    sig_lines = [f"# {cb.name} — Signatures\n"]
    for filename, sigs in sorted(cb.signatures.items()):
        sig_lines.append(f"\n## {filename}\n")
        for s in sigs:
            sig_lines.append(f"- **{s.kind}** `{s.name}` (line {s.line})")
            if s.docstring:
                sig_lines.append(f"  > {s.docstring}")
    sigs_path.write_text("\n".join(sig_lines) + "\n")
    created.append(sigs_path)

    return created
