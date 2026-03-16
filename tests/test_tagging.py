"""Tests for TF-IDF auto-tagging."""

from __future__ import annotations

from papermind.tagging import _tokenize, extract_tags


class TestTokenize:
    """Word tokenization for TF-IDF."""

    def test_extracts_words(self) -> None:
        tokens = _tokenize("SWAT model calibration results")
        assert "swat" in tokens
        assert "calibration" in tokens

    def test_filters_stopwords(self) -> None:
        tokens = _tokenize("the model is very large")
        assert "the" not in tokens
        assert "very" not in tokens

    def test_filters_short(self) -> None:
        tokens = _tokenize("a b cd xyz")
        assert "cd" not in tokens  # too short (2 chars)
        assert "xyz" in tokens


class TestExtractTags:
    """TF-IDF keyword extraction."""

    def test_distinctive_terms(self) -> None:
        corpus = [
            "SWAT model calibration parameter estimation",
            "LSTM neural network deep learning prediction",
            "groundwater recharge aquifer baseflow recession",
        ]
        tags = extract_tags(corpus[0], corpus, max_tags=3)
        assert "swat" in tags or "calibration" in tags

    def test_empty_corpus(self) -> None:
        assert extract_tags("some text", []) == []

    def test_empty_text(self) -> None:
        assert extract_tags("", ["some corpus"]) == []

    def test_max_tags_limit(self) -> None:
        corpus = ["word1 word2 word3 word4 word5 word6 word7 word8 word9"]
        tags = extract_tags(corpus[0], corpus, max_tags=3)
        assert len(tags) <= 3

    def test_common_terms_excluded(self) -> None:
        """Terms appearing in >80% of docs should be excluded."""
        corpus = [
            "water model simulation results",
            "water model calibration output",
            "water model prediction accuracy",
        ]
        tags = extract_tags(corpus[0], corpus, max_tags=5)
        # "water" and "model" appear in all 3 docs (100%) → excluded
        assert "water" not in tags
        assert "model" not in tags
