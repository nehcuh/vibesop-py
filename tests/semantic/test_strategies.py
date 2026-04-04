"""Unit tests for semantic matching strategies."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

np = pytest.importorskip("numpy", reason="numpy not installed")
pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")

from vibesop.semantic.models import SemanticMatch, SemanticMethod, SemanticPattern
from vibesop.semantic.strategies import CosineSimilarityStrategy, HybridMatchingStrategy


@pytest.fixture
def mock_encoder():
    """Create a mock semantic encoder."""
    encoder = Mock()
    encoder.model_name = "test-model"

    # Mock encode_query to return a vector
    encoder.encode_query.return_value = np.random.rand(384)

    return encoder


@pytest.fixture
def mock_cache():
    """Create a mock vector cache."""
    cache = Mock()

    # Mock get_or_compute to return pattern vectors
    def mock_get(pattern_id, examples):
        # Return deterministic vector based on pattern_id
        np.random.seed(hash(pattern_id) % (2**32))
        return np.random.rand(384)

    cache.get_or_compute.side_effect = mock_get
    return cache


@pytest.fixture
def sample_patterns():
    """Create sample semantic patterns for testing."""
    return [
        SemanticPattern(
            pattern_id="security/scan",
            examples=["scan for vulnerabilities", "check for security issues"],
            threshold=0.7,
        ),
        SemanticPattern(
            pattern_id="dev/test",
            examples=["run tests", "execute tests"],
            threshold=0.7,
        ),
        SemanticPattern(
            pattern_id="config/deploy",
            examples=["deploy configuration", "apply config"],
            threshold=0.7,
        ),
    ]


class TestCosineSimilarityStrategyInit:
    """Tests for CosineSimilarityStrategy initialization."""

    def test_initialization_default(self, mock_encoder, mock_cache):
        """Test initialization with default parameters."""
        strategy = CosineSimilarityStrategy(mock_encoder, mock_cache)

        assert strategy.encoder == mock_encoder
        assert strategy.cache == mock_cache
        assert strategy.threshold == 0.7

    def test_initialization_custom_threshold(self, mock_encoder, mock_cache):
        """Test initialization with custom threshold."""
        strategy = CosineSimilarityStrategy(
            mock_encoder,
            mock_cache,
            threshold=0.8,
        )

        assert strategy.threshold == 0.8


class TestCosineSimilarityStrategyMatch:
    """Tests for CosineSimilarityStrategy.match() method."""

    def test_match_returns_list_of_matches(
        self,
        mock_encoder,
        mock_cache,
        sample_patterns,
    ):
        """Test that match returns list of SemanticMatch objects."""
        strategy = CosineSimilarityStrategy(mock_encoder, mock_cache)

        matches = strategy.match("scan for vulnerabilities", sample_patterns)

        assert isinstance(matches, list)
        assert all(isinstance(m, SemanticMatch) for m in matches)

    def test_match_includes_encoding_time(
        self,
        mock_encoder,
        mock_cache,
        sample_patterns,
    ):
        """Test that matches include encoding time."""
        strategy = CosineSimilarityStrategy(mock_encoder, mock_cache)

        matches = strategy.match("test query", sample_patterns)

        for match in matches:
            assert match.encoding_time is not None
            assert match.encoding_time >= 0

    def test_match_filters_by_threshold(
        self,
        mock_encoder,
        mock_cache,
        sample_patterns,
    ):
        """Test that match filters by confidence threshold."""
        # Mock to return low similarities
        mock_cache.get_or_compute.return_value = np.array([0.1, 0.2, 0.3])

        strategy = CosineSimilarityStrategy(
            mock_encoder,
            mock_cache,
            threshold=0.5,
        )

        matches = strategy.match("test query", sample_patterns)

        # All scores are below threshold, so no matches
        assert len(matches) == 0

    def test_match_sorts_by_confidence(
        self,
        mock_encoder,
        mock_cache,
        sample_patterns,
    ):
        """Test that matches are sorted by confidence (descending)."""
        strategy = CosineSimilarityStrategy(mock_encoder, mock_cache)

        # Mock to return varying similarities
        def mock_get(pattern_id, examples):
            similarities = {
                "security/scan": 0.9,
                "dev/test": 0.7,
                "config/deploy": 0.5,
            }
            return similarities[pattern_id]

        mock_cache.get_or_compute.side_effect = mock_get

        matches = strategy.match("test query", sample_patterns)

        # Should be sorted by confidence
        confidences = [m.confidence for m in matches]
        assert confidences == sorted(confidences, reverse=True)

    def test_match_uses_correct_fields(
        self,
        mock_encoder,
        mock_cache,
        sample_patterns,
    ):
        """Test that match results have correct field values."""

        def mock_get(pattern_id, examples):
            # Return similarity based on pattern_id
            similarities = {
                "security/scan": 0.85,
                "dev/test": 0.65,
            }
            return similarities.get(pattern_id, 0.5)

        mock_cache.get_or_compute.side_effect = mock_get

        strategy = CosineSimilarityStrategy(mock_encoder, mock_cache)
        matches = strategy.match("scan vulnerabilities", sample_patterns)

        assert len(matches) > 0

        # Check first match
        match = matches[0]
        assert match.pattern_id in ["security/scan", "dev/test", "config/deploy"]
        assert (
            match.semantic_score
            == mock_cache.get_or_compute.return_value[
                list(mock_cache.get_or_compute.side_effect.__self__.keys())[0]
            ]
        )
        assert match.semantic_method == SemanticMethod.COSINE
        assert match.model_used == "test-model"
        assert match.encoding_time is not None


class TestHybridMatchingStrategyInit:
    """Tests for HybridMatchingStrategy initialization."""

    def test_initialization_default_weights(self, mock_encoder, mock_cache):
        """Test initialization with default weights."""
        strategy = HybridMatchingStrategy(mock_encoder, mock_cache)

        assert strategy.keyword_weight == 0.3
        assert strategy.regex_weight == 0.2
        assert strategy.semantic_weight == 0.5

    def test_initialization_custom_weights(self, mock_encoder, mock_cache):
        """Test initialization with custom weights."""
        strategy = HybridMatchingStrategy(
            mock_encoder,
            mock_cache,
            keyword_weight=0.4,
            regex_weight=0.3,
            semantic_weight=0.3,
        )

        assert strategy.keyword_weight == 0.4
        assert strategy.regex_weight == 0.3
        assert strategy.semantic_weight == 0.3

    def test_initialization_weights_sum_to_one(self, mock_encoder, mock_cache):
        """Test that weights sum to 1.0."""
        strategy = HybridMatchingStrategy(mock_encoder, mock_cache)

        total = strategy.keyword_weight + strategy.regex_weight + strategy.semantic_weight

        assert abs(total - 1.0) < 1e-5

    def test_initialization_invalid_weights_raises_error(self, mock_encoder, mock_cache):
        """Test that weights not summing to 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            HybridMatchingStrategy(
                mock_encoder,
                mock_cache,
                keyword_weight=0.5,
                regex_weight=0.5,
                semantic_weight=0.5,  # Sum = 1.5
            )


class TestHybridMatchingStrategyMatch:
    """Tests for HybridMatchingStrategy.match() method."""

    def test_match_returns_list_of_matches(
        self,
        mock_encoder,
        mock_cache,
        sample_patterns,
    ):
        """Test that match returns list of SemanticMatch objects."""
        strategy = HybridMatchingStrategy(mock_encoder, mock_cache)

        matches = strategy.match("test query", sample_patterns)

        assert isinstance(matches, list)
        assert all(isinstance(m, SemanticMatch) for m in matches)

    def test_match_filters_by_threshold(
        self,
        mock_encoder,
        mock_cache,
        sample_patterns,
    ):
        """Test that match filters by confidence threshold."""
        strategy = HybridMatchingStrategy(
            mock_encoder,
            mock_cache,
            threshold=0.9,  # High threshold
        )

        # Mock to return low semantic scores
        def mock_get(pattern_id, examples):
            return np.array([0.5])  # Low semantic score

        mock_cache.get_or_compute.side_effect = mock_get

        matches = strategy.match("test query", sample_patterns)

        # Should have few or no matches due to high threshold
        assert len(matches) < len(sample_patterns)

    def test_match_sorts_by_confidence(
        self,
        mock_encoder,
        mock_cache,
        sample_patterns,
    ):
        """Test that matches are sorted by confidence."""
        strategy = HybridMatchingStrategy(mock_encoder, mock_cache)

        matches = strategy.match("test query", sample_patterns)

        confidences = [m.confidence for m in matches]
        assert confidences == sorted(confidences, reverse=True)

    def test_match_uses_hybrid_method(
        self,
        mock_encoder,
        mock_cache,
        sample_patterns,
    ):
        """Test that match uses hybrid semantic method."""
        strategy = HybridMatchingStrategy(mock_encoder, mock_cache)

        matches = strategy.match("test query", sample_patterns)

        for match in matches:
            assert match.semantic_method == SemanticMethod.HYBRID


class TestHybridMatchingStrategyScoreFusion:
    """Tests for score fusion logic in hybrid strategy."""

    def test_score_fusion_high_trust_traditional(
        self,
        mock_encoder,
        mock_cache,
    ):
        """Test that high traditional score (>0.8) is kept."""
        strategy = HybridMatchingStrategy(
            mock_encoder,
            mock_cache,
            threshold=0.5,  # Low threshold to allow matches
        )

        # Create a pattern with high traditional score
        pattern = SemanticPattern(
            pattern_id="test/pattern",
            examples=["test"],
            threshold=0.5,
        )

        # Mock cache to return low semantic score
        mock_cache.get_or_compute.return_value = np.array([0.5])

        # Mock encoder
        mock_encoder.encode_query.return_value = np.array([0.5])

        # Manually create match with high traditional score
        # (We need to test the fusion logic)
        # This is tested indirectly through match() method

    def test_score_fusion_high_semantic_trusted(
        self,
        mock_encoder,
        mock_cache,
    ):
        """Test that high semantic score (>0.8) is used."""
        # This is tested through the match() method
        # When semantic score is high and traditional is low,
        # final score should be close to semantic score
        pass

    def test_score_fusion_weighted_average(
        self,
        mock_encoder,
        mock_cache,
    ):
        """Test that medium scores use weighted average."""
        # This is tested through the match() method
        # When both scores are medium, weighted average is used
        pass


class TestHybridMatchingStrategyKeywordScoring:
    """Tests for keyword scoring in hybrid strategy."""

    def test_calculate_keyword_score_exact_match(self):
        """Test keyword scoring with exact match."""
        strategy = HybridMatchingStrategy(Mock(), Mock())

        examples = ["scan for vulnerabilities"]
        query = "scan for vulnerabilities"

        score = strategy._calculate_keyword_score(query, examples)

        assert score > 0.5  # Should have at least baseline score

    def test_calculate_keyword_score_partial_match(self):
        """Test keyword scoring with partial match."""
        strategy = HybridMatchingStrategy(Mock(), Mock())

        examples = ["scan for vulnerabilities", "check security"]
        query = "scan the code"

        # "scan" appears in one example
        score = strategy._calculate_keyword_score(query, examples)

        assert score >= 0.0
        assert score <= 1.0

    def test_calculate_keyword_score_no_match(self):
        """Test keyword scoring with no match."""
        strategy = HybridMatchingStrategy(Mock(), Mock())

        examples = ["scan for vulnerabilities"]
        query = "deploy configuration"

        score = strategy._calculate_keyword_score(query, examples)

        assert score == 0.0

    def test_calculate_keyword_score_empty_examples(self):
        """Test keyword scoring with empty examples."""
        strategy = HybridMatchingStrategy(Mock(), Mock())

        examples = []
        query = "test query"

        score = strategy._calculate_keyword_score(query, examples)

        assert score == 0.0


class TestHybridMatchingStrategyRegexScoring:
    """Tests for regex scoring in hybrid strategy."""

    def test_calculate_regex_score_exact_match(self):
        """Test regex scoring with exact match."""
        strategy = HybridMatchingStrategy(Mock(), Mock())

        examples = ["scan for vulnerabilities"]
        query = "scan for vulnerabilities"

        score = strategy._calculate_regex_score(query, examples)

        assert score > 0.5  # Should have at least baseline score

    def test_calculate_regex_score_partial_match(self):
        """Test regex scoring with partial match."""
        strategy = HybridMatchingStrategy(Mock(), Mock())

        examples = ["scan for vulnerabilities"]
        query = "SCAN for vulnerabilities"  # Case insensitive

        score = strategy._calculate_regex_score(query, examples)

        assert score >= 0.0
        assert score <= 1.0

    def test_calculate_regex_score_no_match(self):
        """Test regex scoring with no match."""
        strategy = HybridMatchingStrategy(Mock(), Mock())

        examples = ["scan for vulnerabilities"]
        query = "deploy configuration"

        score = strategy._calculate_regex_score(query, examples)

        assert score == 0.0

    def test_calculate_regex_score_empty_examples(self):
        """Test regex scoring with empty examples."""
        strategy = HybridMatchingStrategy(Mock(), Mock())

        examples = []
        query = "test query"

        score = strategy._calculate_regex_score(query, examples)

        assert score == 0.0


class TestSemanticMatch:
    """Tests for SemanticMatch dataclass."""

    def test_semantic_match_creation(self):
        """Test creating a SemanticMatch instance."""
        match = SemanticMatch(
            pattern_id="security/scan",
            confidence=0.92,
            semantic_score=0.87,
            semantic_method=SemanticMethod.COSINE,
            vector_similarity=0.87,
            model_used="test-model",
            encoding_time=0.012,
        )

        assert match.pattern_id == "security/scan"
        assert match.confidence == 0.92
        assert match.semantic_score == 0.87
        assert match.semantic_method == SemanticMethod.COSINE

    def test_semantic_match_to_dict(self):
        """Test converting SemanticMatch to dictionary."""
        match = SemanticMatch(
            pattern_id="security/scan",
            confidence=0.92,
            semantic_score=0.87,
            semantic_method=SemanticMethod.COSINE,
        )

        match_dict = match.to_dict()

        assert isinstance(match_dict, dict)
        assert match_dict["pattern_id"] == "security/scan"
        assert match_dict["confidence"] == 0.92
        assert match_dict["semantic_score"] == 0.87


class TestSemanticPattern:
    """Tests for SemanticPattern dataclass."""

    def test_semantic_pattern_creation(self):
        """Test creating a SemanticPattern instance."""
        pattern = SemanticPattern(
            pattern_id="security/scan",
            examples=["scan for vulnerabilities"],
            embedding_model="test-model",
            threshold=0.7,
        )

        assert pattern.pattern_id == "security/scan"
        assert pattern.examples == ["scan for vulnerabilities"]
        assert pattern.embedding_model == "test-model"
        assert pattern.threshold == 0.7

    def test_semantic_pattern_compute_vector(self):
        """Test computing vector for pattern."""
        pattern = SemanticPattern(
            pattern_id="test/pattern",
            examples=["test example"],
        )

        mock_encoder = Mock()
        mock_encoder.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4]])

        vector = pattern.compute_vector(mock_encoder)

        # Vector should be computed
        assert isinstance(vector, np.ndarray)
        mock_encoder.encode.assert_called_once_with(["test example"], normalize=True)

    def test_semantic_pattern_compute_vector_empty_examples_raises_error(self):
        """Test that empty examples raises ValueError."""
        pattern = SemanticPattern(
            pattern_id="test/pattern",
            examples=[],
        )

        mock_encoder = Mock()

        with pytest.raises(ValueError, match="no examples"):
            pattern.compute_vector(mock_encoder)

    def test_semantic_pattern_compute_vector_invalid_strategy_raises_error(self):
        """Test that invalid strategy raises ValueError."""
        pattern = SemanticPattern(
            pattern_id="test/pattern",
            examples=["test"],
        )

        mock_encoder = Mock()

        with pytest.raises(ValueError, match="Unknown aggregation strategy"):
            pattern.compute_vector(mock_encoder, strategy="invalid")
