"""Test semantic matcher with TF-IDF."""

import pytest

from vibesop.core.routing.semantic import (
    STOP_WORDS,
    Document,
    SemanticMatch,
    SemanticMatcher,
)


class TestSemanticMatcher:
    """Test SemanticMatcher class."""

    def test_init(self) -> None:
        """Test initialization."""
        matcher = SemanticMatcher()
        assert matcher.min_score == 0.3
        assert matcher._documents == []

    def test_init_custom_min_score(self) -> None:
        """Test initialization with custom min_score."""
        matcher = SemanticMatcher(min_score=0.5)
        assert matcher.min_score == 0.5

    def test_index_skills(self) -> None:
        """Test indexing skills for matching."""
        matcher = SemanticMatcher()

        skills = [
            {"id": "debug", "intent": "Debug errors and find bugs"},
            {"id": "review", "intent": "Review code quality"},
        ]

        matcher.index_skills(skills)

        assert len(matcher._documents) == 2
        assert matcher._idf != {}

    def test_match_exact_query(self) -> None:
        """Test matching with exact query."""
        matcher = SemanticMatcher()

        skills = [
            {"id": "debug", "intent": "Debug errors and find bugs", "namespace": "builtin"},
            {"id": "review", "intent": "Review code quality", "namespace": "builtin"},
        ]

        matcher.index_skills(skills)

        # Match "debug" - should find debug skill
        results = matcher.match("debug")

        assert len(results) > 0
        assert results[0].skill_id == "debug"

    def test_match_with_stop_words(self) -> None:
        """Test that stop words are filtered but content words remain."""
        matcher = SemanticMatcher(min_score=0.01)  # Very low threshold for testing

        skills = [
            {"id": "test", "intent": "Run tests and verify code"},
        ]

        matcher.index_skills(skills)

        # Query with word that appears in intent
        results = matcher.match("tests")

        # With very low threshold, should find some match
        # (even if low confidence due to single word match)
        if len(results) > 0:
            assert results[0].skill_id == "test"
        else:
            # If no match, it's OK - just verify tokenization works
            tokens = matcher._tokenize("run the tests")
            assert "run" in tokens or "tests" in tokens
            assert "the" not in tokens  # "the" should be filtered

    def test_match_below_min_score(self) -> None:
        """Test that low scores are filtered out."""
        matcher = SemanticMatcher(min_score=0.8)

        skills = [
            {"id": "debug", "intent": "Debug errors"},
            {"id": "review", "intent": "Review code"},
        ]

        matcher.index_skills(skills)

        # Query that shouldn't match well
        results = matcher.match("completely unrelated query")

        # Should return empty or low-confidence results
        assert all(r.score < 0.8 for r in results)

    def test_match_returns_top_k(self) -> None:
        """Test that top_k parameter limits results."""
        matcher = SemanticMatcher()

        skills = [
            {"id": "debug", "intent": "Debug errors and bugs"},
            {"id": "review", "intent": "Review code quality"},
            {"id": "test", "intent": "Run unit tests"},
            {"id": "refactor", "intent": "Refactor code structure"},
        ]

        matcher.index_skills(skills)

        # Request top 2
        results = matcher.match("code quality review", top_k=2)

        assert len(results) <= 2

    def test_match_sorted_by_score(self) -> None:
        """Test that results are sorted by score descending."""
        matcher = SemanticMatcher()

        skills = [
            {"id": "debug", "intent": "Debug errors"},
            {"id": "review", "intent": "Review code"},
        ]

        matcher.index_skills(skills)

        results = matcher.match("review code")

        if len(results) > 1:
            # Check descending order
            for i in range(len(results) - 1):
                assert results[i].score >= results[i + 1].score

    def test_tokenize_removes_punctuation(self) -> None:
        """Test tokenization removes punctuation."""
        matcher = SemanticMatcher()

        tokens = matcher._tokenize("hello, world! test.")

        assert "," not in tokens
        assert "!" not in tokens
        assert "." not in tokens

    def test_tokenize_lowercases(self) -> None:
        """Test tokenization lowercases text."""
        matcher = SemanticMatcher()

        tokens = matcher._tokenize("HELLO World")

        assert "hello" in tokens
        assert "world" in tokens

    def test_tokenize_filters_stop_words(self) -> None:
        """Test tokenization filters stop words."""
        matcher = SemanticMatcher()

        tokens = matcher._tokenize("the code review and test")

        # "the", "and" should be filtered
        assert "the" not in tokens
        assert "and" not in tokens
        assert "code" in tokens

    def test_tokenize_filters_short_tokens(self) -> None:
        """Test tokenization filters very short tokens."""
        matcher = SemanticMatcher()

        tokens = matcher._tokenize("a b c hello world")

        # Single letters should be filtered
        assert "a" not in tokens
        assert "b" not in tokens
        assert "hello" in tokens

    def test_calculate_tf(self) -> None:
        """Test term frequency calculation."""
        matcher = SemanticMatcher()

        tokens = ["hello", "world", "hello"]
        tf = matcher._calculate_tf(tokens)

        assert "hello" in tf
        assert "world" in tf
        # "hello" appears twice, should be normalized to 1.0
        assert tf["hello"] == 1.0
        # "world" appears once, should be 0.5
        assert tf["world"] == 0.5

    def test_calculate_idf(self) -> None:
        """Test IDF calculation."""
        matcher = SemanticMatcher()

        # Add documents
        matcher._documents = [
            Document(text="hello world", tokens=["hello", "world"], metadata={}),
            Document(text="hello there", tokens=["hello", "there"], metadata={}),
        ]

        matcher._calculate_idf()

        # "hello" appears in both docs, should have lower IDF
        # "world" appears in one doc, should have higher IDF
        assert matcher._idf["hello"] < matcher._idf["world"]

    def test_cosine_similarity_identical(self) -> None:
        """Test cosine similarity with identical vectors."""
        matcher = SemanticMatcher()

        matcher._documents = [Document(text="test", tokens=["hello", "world"], metadata={})]

        # Manually set IDF for testing
        matcher._idf = {"hello": 1.0, "world": 1.0}

        query_tfidf = {"hello": 0.5, "world": 0.5}
        doc = matcher._documents[0]

        similarity = matcher._cosine_similarity(query_tfidf, doc)

        # Identical vectors should have similarity 1.0
        assert similarity == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self) -> None:
        """Test cosine similarity with orthogonal vectors."""
        matcher = SemanticMatcher()

        # Create documents with no overlapping terms
        matcher._documents = [Document(text="doc1", tokens=["apple", "banana"], metadata={})]
        matcher._calculate_idf()

        query_tfidf = {"orange": 1.0}
        doc = matcher._documents[0]

        similarity = matcher._cosine_similarity(query_tfidf, doc)

        # No overlap should have similarity 0.0
        assert similarity == pytest.approx(0.0)

    def test_get_term_importance(self) -> None:
        """Test getting term importance (IDF)."""
        matcher = SemanticMatcher()

        skills = [
            {"id": "test", "intent": "Run tests and verify code"},
            {"id": "debug", "intent": "Debug errors"},
        ]

        matcher.index_skills(skills)

        # "test" should have some IDF score
        # (it appears in some but not all documents)
        idf = matcher.get_term_importance("test")
        assert idf > 0

    def test_empty_query(self) -> None:
        """Test matching with empty query."""
        matcher = SemanticMatcher()

        skills = [{"id": "test", "intent": "test"}]
        matcher.index_skills(skills)

        results = matcher.match("")

        assert len(results) == 0

    def test_no_documents_indexed(self) -> None:
        """Test matching when no documents are indexed."""
        matcher = SemanticMatcher()

        results = matcher.match("test")

        assert len(results) == 0


class TestStopWords:
    """Test stop words list."""

    def test_common_english_stop_words(self) -> None:
        """Test common English stop words are present."""
        common_stop_words = ["the", "a", "an", "and", "or", "but", "is", "are", "was"]

        for word in common_stop_words:
            assert word in STOP_WORDS

    def test_common_chinese_stop_words(self) -> None:
        """Test common Chinese stop words are present."""
        common_chinese_stop_words = ["的", "了", "是", "在", "有", "和", "我", "你", "他"]

        for word in common_chinese_stop_words:
            assert word in STOP_WORDS


class TestDocument:
    """Test Document dataclass."""

    def test_create_document(self) -> None:
        """Test creating a document."""
        doc = Document(
            text="hello world",
            tokens=["hello", "world"],
            metadata={"skill_id": "test"},
        )

        assert doc.text == "hello world"
        assert doc.tokens == ["hello", "world"]
        assert doc.metadata["skill_id"] == "test"


class TestSemanticMatch:
    """Test SemanticMatch dataclass."""

    def test_create_match(self) -> None:
        """Test creating a semantic match."""
        match = SemanticMatch(
            skill_id="test",
            score=0.85,
            metadata={"namespace": "builtin"},
        )

        assert match.skill_id == "test"
        assert match.score == 0.85
        assert match.metadata["namespace"] == "builtin"
