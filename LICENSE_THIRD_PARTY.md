# Third-Party Licenses

This document lists all runtime dependencies of PaperMind and their licenses.

---

## Python Runtime Dependencies

### typer
- **License**: MIT
- **URL**: https://github.com/tiangolo/typer
- **Used for**: CLI framework

### httpx
- **License**: BSD-3-Clause
- **URL**: https://github.com/encode/httpx
- **Used for**: HTTP client for paper downloads and API calls

### griffe
- **License**: ISC
- **URL**: https://github.com/mkdocstrings/griffe
- **Used for**: Python package API extraction (introspection without import)

### PyYAML
- **License**: MIT
- **URL**: https://github.com/yaml/pyyaml
- **Used for**: YAML parsing in config and frontmatter

### python-frontmatter
- **License**: MIT
- **URL**: https://github.com/eyeseast/python-frontmatter
- **Used for**: Reading and writing YAML frontmatter in markdown files

### rich
- **License**: MIT
- **URL**: https://github.com/Textualize/rich
- **Used for**: Terminal output formatting

### Jinja2
- **License**: BSD-3-Clause
- **URL**: https://github.com/pallets/jinja
- **Used for**: Markdown rendering templates for package API docs

### mcp
- **License**: MIT
- **URL**: https://github.com/modelcontextprotocol/python-sdk
- **Used for**: MCP server implementation (stdio transport)

---

## Optional Python Dependencies

### playwright
- **License**: Apache-2.0
- **URL**: https://github.com/microsoft/playwright-python
- **Used for**: Browser-based ingestion of JavaScript-rendered package documentation
- **Install**: `pip install "papermind[browser]"`

---

## Optional OCR Dependencies (papermind[ocr])

### transformers
- **License**: Apache-2.0
- **URL**: https://github.com/huggingface/transformers
- **Used for**: Loading and running GLM-OCR model for PDF conversion

### torch (PyTorch)
- **License**: BSD-3-Clause
- **URL**: https://github.com/pytorch/pytorch
- **Used for**: Model inference backend

### pymupdf
- **License**: AGPL-3.0 (with commercial license available)
- **URL**: https://github.com/pymupdf/PyMuPDF
- **Used for**: PDF page rendering to images for OCR

### GLM-OCR (model weights)
- **License**: MIT
- **URL**: https://huggingface.co/zai-org/GLM-OCR
- **Used for**: PDF to markdown OCR conversion
- **Note**: Model weights downloaded from HuggingFace on first use

## External Tools (subprocess)

### qmd
- **License**: See upstream project for current license
- **URL**: https://github.com/simonw/qmd
- **Used for**: Semantic vector search over the knowledge base
- **Note**: Optional. PaperMind falls back to grep-based search when qmd is not available.

---

## Development Dependencies

These are only required during development and testing, not at runtime.

### pytest
- **License**: MIT
- **URL**: https://github.com/pytest-dev/pytest

### pytest-asyncio
- **License**: Apache-2.0
- **URL**: https://github.com/pytest-dev/pytest-asyncio

### ruff
- **License**: MIT
- **URL**: https://github.com/astral-sh/ruff
