"""Tests for citation graph features — cites/cited_by in PaperResult and SS parsing."""

from __future__ import annotations

from papermind.discovery.base import PaperResult
from papermind.discovery.semantic_scholar import SemanticScholarProvider


class TestPaperResultCitationFields:
    """PaperResult should carry cites and cited_by lists."""

    def test_default_empty_lists(self) -> None:
        r = PaperResult(title="Test")
        assert r.cites == []
        assert r.cited_by == []

    def test_cites_stored(self) -> None:
        r = PaperResult(title="Test", cites=["10.1/A", "10.1/B"])
        assert r.cites == ["10.1/A", "10.1/B"]

    def test_cited_by_stored(self) -> None:
        r = PaperResult(title="Test", cited_by=["10.1/C"])
        assert r.cited_by == ["10.1/C"]


class TestSemanticScholarCitationParsing:
    """Semantic Scholar provider should extract citation DOIs."""

    def test_extract_dois_from_references(self) -> None:
        provider = SemanticScholarProvider()
        refs = [
            {"externalIds": {"DOI": "10.1/ref-a"}},
            {"externalIds": {"DOI": "10.1/ref-b"}},
            {"externalIds": {}},  # no DOI
            {"externalIds": None},  # None externalIds
        ]
        dois = provider._extract_dois(refs)
        assert dois == ["10.1/ref-a", "10.1/ref-b"]

    def test_extract_dois_empty_list(self) -> None:
        provider = SemanticScholarProvider()
        assert provider._extract_dois([]) == []

    def test_extract_dois_non_dict_entries_skipped(self) -> None:
        provider = SemanticScholarProvider()
        assert provider._extract_dois([None, "garbage", 42]) == []

    def test_parse_includes_citations(self) -> None:
        provider = SemanticScholarProvider()
        raw = {
            "title": "Test Paper",
            "authors": [],
            "year": 2023,
            "abstract": "",
            "externalIds": {"DOI": "10.1/main"},
            "isOpenAccess": True,
            "venue": "",
            "citationCount": 5,
            "openAccessPdf": None,
            "references": [
                {"externalIds": {"DOI": "10.1/ref-1"}},
                {"externalIds": {"DOI": "10.1/ref-2"}},
            ],
            "citations": [
                {"externalIds": {"DOI": "10.1/citer-1"}},
            ],
        }
        result = provider._parse(raw)
        assert result.cites == ["10.1/ref-1", "10.1/ref-2"]
        assert result.cited_by == ["10.1/citer-1"]

    def test_parse_handles_missing_references(self) -> None:
        provider = SemanticScholarProvider()
        raw = {
            "title": "No Refs",
            "authors": [],
            "year": 2023,
            "abstract": "",
            "externalIds": {},
            "isOpenAccess": False,
            "venue": "",
            "citationCount": 0,
            "openAccessPdf": None,
        }
        result = provider._parse(raw)
        assert result.cites == []
        assert result.cited_by == []
