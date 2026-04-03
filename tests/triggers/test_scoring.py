"""Tests for scoring algorithms."""

import pytest
import math

from vibesop.triggers.utils import (
    tokenize,
    calculate_tf,
    calculate_idf,
    calculate_tfidf,
    cosine_similarity,
    calculate_keyword_match_score,
    calculate_regex_match_score,
    calculate_combined_score,
)


class TestTokenize:
    """Test text tokenization."""

    def test_simple_english(self):
        """Test tokenizing simple English text."""
        result = tokenize("Hello, World!")
        assert result == ["hello", "world"]

    def test_empty_string(self):
        """Test tokenizing empty string."""
        assert tokenize("") == []
        assert tokenize("   ") == []

    def test_punctuation_removal(self):
        """Test punctuation is removed."""
        result = tokenize("Hello, world! How are you?")
        assert "hello" in result
        assert "world" in result
        assert "how" in result
        assert "are" in result
        assert "you" in result
        assert "," not in result
        assert "!" not in result
        assert "?" not in result

    def test_case_insensitive(self):
        """Test lowercasing."""
        assert tokenize("HELLO") == ["hello"]
        assert tokenize("HeLLo WoRLd") == ["hello", "world"]

    def test_chinese_characters(self):
        """Test Chinese character tokenization."""
        result = tokenize("扫描安全漏洞")
        assert "扫描" in result
        assert "安全" in result
        assert "漏洞" in result

    def test_mixed_language(self):
        """Test mixed English and Chinese."""
        result = tokenize("scan 安全漏洞")
        assert "scan" in result
        assert "安全" in result


class TestTermFrequency:
    """Test TF calculation."""

    def test_basic_tf(self):
        """Test basic TF calculation."""
        result = calculate_tf(["hello", "world", "hello"])
        assert result["hello"] == 2/3
        assert result["world"] == 1/3

    def test_empty_tokens(self):
        """Test TF with empty token list."""
        assert calculate_tf([]) == {}

    def test_single_token(self):
        """Test TF with single token."""
        result = calculate_tf(["hello"])
        assert result["hello"] == 1.0


class TestInverseDocumentFrequency:
    """Test IDF calculation."""

    def test_basic_idf(self):
        """Test basic IDF calculation."""
        docs = [
            ["hello", "world"],
            ["hello", "test"]
        ]
        result = calculate_idf(docs)

        # "hello" appears in both docs - lower IDF
        assert result["hello"] < result["world"]
        assert result["hello"] < result["test"]

        # "world" and "test" appear in one doc each - same IDF
        assert math.isclose(result["world"], result["test"], rel_tol=0.01)

    def test_empty_documents(self):
        """Test IDF with empty document list."""
        assert calculate_idf([]) == {}

    def test_single_document(self):
        """Test IDF with single document."""
        docs = [["hello", "world"]]
        result = calculate_idf(docs)

        assert "hello" in result
        assert "world" in result
        # All terms have same IDF when in single doc
        assert math.isclose(result["hello"], result["world"])


class TestTFIDF:
    """Test TF-IDF calculation."""

    def test_basic_tfidf(self):
        """Test basic TF-IDF calculation."""
        tokens = ["hello", "world", "hello"]
        idf = {"hello": 1.0, "world": 2.0}

        result = calculate_tfidf(tokens, idf)

        # hello: TF=2/3, IDF=1.0 => 0.667
        assert math.isclose(result["hello"], 0.667, rel_tol=0.01)

        # world: TF=1/3, IDF=2.0 => 0.667
        assert math.isclose(result["world"], 0.667, rel_tol=0.01)

    def test_missing_idf(self):
        """Test TF-IDF with missing IDF (should use 1.0)."""
        tokens = ["hello", "world"]
        idf = {"hello": 1.5}

        result = calculate_tfidf(tokens, idf)

        # hello: TF=0.5, IDF=1.5 => 0.75
        assert math.isclose(result["hello"], 0.75, rel_tol=0.01)

        # world: TF=0.5, IDF=1.0 (default) => 0.5
        assert math.isclose(result["world"], 0.5, rel_tol=0.01)


class TestCosineSimilarity:
    """Test cosine similarity calculation."""

    def test_identical_vectors(self):
        """Test cosine similarity of identical vectors."""
        vec1 = {"hello": 1.0, "world": 0.5}
        vec2 = {"hello": 1.0, "world": 0.5}

        result = cosine_similarity(vec1, vec2)
        # Use isclose for floating point comparison
        assert math.isclose(result, 1.0, rel_tol=0.01)

    def test_orthogonal_vectors(self):
        """Test cosine similarity of orthogonal vectors."""
        vec1 = {"hello": 1.0}
        vec2 = {"world": 1.0}

        result = cosine_similarity(vec1, vec2)
        assert result == 0.0

    def test_partial_overlap(self):
        """Test cosine similarity with partial overlap."""
        vec1 = {"hello": 1.0, "world": 0.5}
        vec2 = {"hello": 0.5, "world": 1.0}

        result = cosine_similarity(vec1, vec2)
        assert 0.0 < result < 1.0

    def test_empty_vectors(self):
        """Test cosine similarity with empty vectors."""
        assert cosine_similarity({}, {"hello": 1.0}) == 0.0
        assert cosine_similarity({"hello": 1.0}, {}) == 0.0
        assert cosine_similarity({}, {}) == 0.0

    def test_opposite_vectors(self):
        """Test cosine similarity (should be positive since TF-IDF is non-negative)."""
        vec1 = {"hello": 1.0}
        vec2 = {"hello": 0.5}

        result = cosine_similarity(vec1, vec2)
        assert result == 1.0  # Same direction


class TestKeywordMatchScore:
    """Test keyword matching score."""

    def test_all_keywords_match(self):
        """Test when all keywords match."""
        result = calculate_keyword_match_score(
            "scan security vulnerabilities",
            ["scan", "security", "vulnerabilities"]
        )
        assert result == 1.0

    def test_partial_keyword_match(self):
        """Test when some keywords match."""
        result = calculate_keyword_match_score(
            "scan code",
            ["scan", "security", "vulnerabilities"]
        )
        assert result == 1/3

    def test_no_keywords_match(self):
        """Test when no keywords match."""
        result = calculate_keyword_match_score(
            "run tests",
            ["scan", "security"]
        )
        assert result == 0.0

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        result = calculate_keyword_match_score(
            "SCAN Security",
            ["scan", "security"]
        )
        assert result == 1.0

    def test_empty_keywords(self):
        """Test with empty keyword list."""
        result = calculate_keyword_match_score("test", [])
        assert result == 0.0


class TestRegexMatchScore:
    """Test regex matching score."""

    def test_all_patterns_match(self):
        """Test when all patterns match."""
        result = calculate_regex_match_score(
            "scan security and security scan",
            [r"scan.*security", r"security.*scan"]
        )
        # Both patterns should match the text
        assert result == 1.0

    def test_partial_pattern_match(self):
        """Test when some patterns match."""
        result = calculate_regex_match_score(
            "scan code",
            [r"scan.*security", r"scan.*code"]
        )
        assert result == 0.5

    def test_no_patterns_match(self):
        """Test when no patterns match."""
        result = calculate_regex_match_score(
            "run tests",
            [r"scan.*security"]
        )
        assert result == 0.0

    def test_empty_patterns(self):
        """Test with empty pattern list."""
        result = calculate_regex_match_score("test", [])
        assert result == 0.0


class TestCombinedScore:
    """Test combined score calculation."""

    def test_default_weights(self):
        """Test combined score with default weights."""
        result = calculate_combined_score(
            keyword_score=1.0,
            regex_score=0.5,
            semantic_score=0.8
        )

        # 1.0 * 0.4 + 0.5 * 0.3 + 0.8 * 0.3 = 0.79
        assert math.isclose(result, 0.79, rel_tol=0.01)

    def test_custom_weights(self):
        """Test combined score with custom weights."""
        result = calculate_combined_score(
            keyword_score=1.0,
            regex_score=0.5,
            semantic_score=0.8,
            weights=(0.5, 0.3, 0.2)
        )

        # 1.0 * 0.5 + 0.5 * 0.3 + 0.8 * 0.2 = 0.81
        assert math.isclose(result, 0.81, rel_tol=0.01)

    def test_invalid_weights(self):
        """Test that invalid weights raise error."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            calculate_combined_score(
                keyword_score=1.0,
                regex_score=0.5,
                semantic_score=0.8,
                weights=(0.5, 0.3, 0.3)  # Sum = 1.1
            )

    def test_score_clamping(self):
        """Test that scores are clamped between 0.0 and 1.0."""
        # Test upper bound
        result = calculate_combined_score(
            keyword_score=2.0,
            regex_score=2.0,
            semantic_score=2.0
        )
        assert result <= 1.0

    def test_all_zero_scores(self):
        """Test with all zero scores."""
        result = calculate_combined_score(0.0, 0.0, 0.0)
        assert result == 0.0

    def test_all_perfect_scores(self):
        """Test with all perfect scores."""
        result = calculate_combined_score(1.0, 1.0, 1.0)
        assert result == 1.0
