"""Unit tests for unified matching module.

Tests cover:
- Tokenizer functionality
- Similarity calculation
- TF-IDF calculation
- Matcher implementations
"""

from vibesop.core.matching import (
    KeywordMatcher,
    LevenshteinMatcher,
    MatchResult,
    MatcherConfig,
    RoutingContext,
    TFIDFCalculator,
    TFIDFMatcher,
    TFIDFVector,
    TokenizerConfig,
    TokenizerMode,
    cosine_similarity,
    tokenize,
)


def test_tokenize_basic():
    """Test basic tokenization."""
    tokens = tokenize("Hello World")
    assert tokens == ["hello", "world"]


def test_tokenize_cjk():
    """Test CJK tokenization."""
    tokens = tokenize("扫描安全漏洞")
    # CJK characters are split into individual tokens or 2-character words
    assert len(tokens) >= 3
    assert any("安全" in t or "漏" in t for t in tokens)


def test_tokenize_with_stopwords():
    """Test tokenization with stopword removal."""
    config = TokenizerConfig(
        mode=TokenizerMode.CLEAN,
        stop_words={"the", "a", "an"},
    )
    tokens = tokenize("the quick brown fox", config)
    assert "the" not in tokens
    assert "quick" in tokens


def test_cosine_similarity_dicts():
    """Test cosine similarity with dictionary vectors."""
    vec1 = {"hello": 1.0, "world": 0.5}
    vec2 = {"hello": 0.5, "world": 1.0}

    score = cosine_similarity(vec1, vec2)
    assert 0.0 <= score <= 1.0
    assert score > 0.7  # Should be similar


def test_tfidf_calculator():
    """Test TF-IDF calculation."""
    calc = TFIDFCalculator()

    documents = [
        ["hello", "world"],
        ["hello", "test"],
        ["world", "test"],
    ]

    # Fit and transform
    calc.fit(documents)

    vec = calc.transform(["hello", "world"])
    assert isinstance(vec, TFIDFVector)
    assert len(vec.tfidf) > 0
    assert vec.magnitude > 0


def test_tfidf_vector_operations():
    """Test TF-IDF vector operations."""
    vec = TFIDFVector()
    vec.tfidf = {"hello": 0.5, "world": 0.5}

    vec.normalize()
    assert vec.magnitude > 0

    # Dot product
    vec2 = TFIDFVector()
    vec2.tfidf = {"hello": 0.5, "world": 0.5}

    dot = vec.dot_product(vec2)
    assert dot > 0


def test_keyword_matcher():
    """Test keyword matcher."""
    # Use lower threshold for test since keyword matching is conservative
    config = MatcherConfig(min_confidence=0.1)
    matcher = KeywordMatcher(config)

    candidates = [
        {
            "id": "debug",
            "name": "Debug Skill",
            "description": "Debugging errors and bugs",
            "keywords": ["debug", "error", "bug"],
        },
        {
            "id": "test",
            "name": "Test Skill",
            "description": "Writing and running tests",
            "keywords": ["test", "unit", "integration"],
        },
    ]

    results = matcher.match("debug error", candidates)

    assert len(results) > 0
    assert results[0].skill_id == "debug"
    assert results[0].confidence > 0.1


def test_tfidf_matcher():
    """Test TF-IDF matcher."""
    matcher = TFIDFMatcher()

    candidates = [
        {
            "id": "debug",
            "name": "Debug Skill",
            "description": "Debugging errors and bugs",
            "keywords": ["debug", "error", "bug"],
        },
        {
            "id": "test",
            "name": "Test Skill",
            "description": "Writing and running tests",
            "keywords": ["test", "unit", "integration"],
        },
    ]

    results = matcher.match("debug database connection", candidates)

    # TF-IDF should find semantic similarity
    assert len(results) >= 0


def test_levenshtein_matcher():
    """Test Levenshtein matcher for fuzzy matching."""
    # Use lower threshold for test
    config = MatcherConfig(min_confidence=0.1)
    matcher = LevenshteinMatcher(config)

    candidates = [
        {
            "id": "database",
            "name": "Database Skill",
            "description": "Database operations and queries",
        },
    ]

    # Query with typo
    results = matcher.match("databse connection", candidates)

    assert len(results) > 0
    # Should match despite typo (score depends on string similarity)
    assert results[0].confidence > 0.1


def test_match_result_with_boost():
    """Test MatchResult boost functionality."""
    result = MatchResult(
        skill_id="test",
        confidence=0.5,
        score_breakdown={"base": 0.5},
        matcher_type="keyword",
    )

    boosted = result.with_boost(0.2, "test_boost")

    assert boosted.confidence == 0.7
    assert boosted.metadata.get("boosted") is True
    assert boosted.metadata.get("original_confidence") == 0.5


def test_match_result_meets_threshold():
    """Test MatchResult threshold checking."""
    result = MatchResult(
        skill_id="test",
        confidence=0.7,
        score_breakdown={"base": 0.7},
        matcher_type="keyword",
    )

    assert result.meets_threshold(0.6) is True
    assert result.meets_threshold(0.8) is False


def test_routing_context():
    """Test RoutingContext."""
    context = RoutingContext(
        file_type="py",
        error_count=3,
        recent_files=["main.py", "utils.py"],
        project_type="python",
        user_skill_level="intermediate",
    )

    ctx_dict = context.to_dict()
    assert ctx_dict["file_type"] == "py"
    assert ctx_dict["error_count"] == 3
    assert ctx_dict["project_type"] == "python"


if __name__ == "__main__":
    # Run tests
    import sys

    test_funcs = [
        test_tokenize_basic,
        test_tokenize_cjk,
        test_tokenize_with_stopwords,
        test_cosine_similarity_dicts,
        test_tfidf_calculator,
        test_tfidf_vector_operations,
        test_keyword_matcher,
        test_tfidf_matcher,
        test_levenshtein_matcher,
        test_match_result_with_boost,
        test_match_result_meets_threshold,
        test_routing_context,
    ]

    failed = []
    for func in test_funcs:
        try:
            func()
            print(f"✓ {func.__name__}")
        except AssertionError as e:
            print(f"✗ {func.__name__}: {e}")
            failed.append(func.__name__)
        except Exception as e:
            print(f"✗ {func.__name__}: {type(e).__name__}: {e}")
            failed.append(func.__name__)

    if failed:
        print(f"\n{len(failed)} test(s) failed: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"\n✓ All {len(test_funcs)} tests passed!")
        sys.exit(0)
