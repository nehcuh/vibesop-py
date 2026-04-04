"""Comprehensive tests for semantic models module.

Tests all public classes and methods in vibesop.semantic.models:
- SemanticMethod enum
- SemanticPattern dataclass
- SemanticMatch dataclass
- EncoderConfig Pydantic model
- SemanticConfig Pydantic model
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

np = pytest.importorskip("numpy", reason="numpy not installed")

from vibesop.semantic.models import (
    EncoderConfig,
    SemanticConfig,
    SemanticMatch,
    SemanticMethod,
    SemanticPattern,
)


class TestSemanticMethod:
    """Tests for SemanticMethod enum."""

    def test_cosine_value(self):
        """Test COSINE enum value."""
        assert SemanticMethod.COSINE == "cosine"

    def test_hybrid_value(self):
        """Test HYBRID enum value."""
        assert SemanticMethod.HYBRID == "hybrid"

    def test_is_string_subtype(self):
        """Test that SemanticMethod is a string enum."""
        assert isinstance(SemanticMethod.COSINE, str)
        assert isinstance(SemanticMethod.HYBRID, str)

    def test_enum_members_count(self):
        """Test that there are exactly two enum members."""
        assert len(SemanticMethod) == 2

    def test_enum_iteration(self):
        """Test enum iteration."""
        members = list(SemanticMethod)
        assert SemanticMethod.COSINE in members
        assert SemanticMethod.HYBRID in members

    def test_enum_from_string(self):
        """Test creating enum from string value."""
        assert SemanticMethod("cosine") == SemanticMethod.COSINE
        assert SemanticMethod("hybrid") == SemanticMethod.HYBRID


class TestSemanticPattern:
    """Tests for SemanticPattern dataclass."""

    def test_default_values(self):
        """Test default field values."""
        pattern = SemanticPattern(
            pattern_id="test/pattern",
            examples=["example 1"],
        )

        assert pattern.pattern_id == "test/pattern"
        assert pattern.examples == ["example 1"]
        assert pattern.vector is None
        assert pattern.embedding_model == "paraphrase-multilingual-MiniLM-L12-v2"
        assert pattern.threshold == 0.7

    def test_custom_values(self):
        """Test custom field values."""
        pattern = SemanticPattern(
            pattern_id="security/scan",
            examples=["scan for vulns", "check security"],
            embedding_model="all-MiniLM-L6-v2",
            threshold=0.85,
        )

        assert pattern.pattern_id == "security/scan"
        assert pattern.examples == ["scan for vulns", "check security"]
        assert pattern.embedding_model == "all-MiniLM-L6-v2"
        assert pattern.threshold == 0.85
        assert pattern.vector is None

    def test_with_precomputed_vector(self):
        """Test pattern with pre-computed vector."""
        vector = np.array([0.1, 0.2, 0.3])
        pattern = SemanticPattern(
            pattern_id="test",
            examples=["example"],
            vector=vector,
        )

        assert np.array_equal(pattern.vector, vector)

    def test_compute_vector_mean_strategy(self):
        """Test vector computation with mean strategy."""
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = np.array(
            [
                [0.5, 0.5, 0.0],
                [0.0, 0.5, 0.5],
            ]
        )

        pattern = SemanticPattern(
            pattern_id="test/mean",
            examples=["example 1", "example 2"],
        )

        result = pattern.compute_vector(mock_encoder, strategy="mean")

        mock_encoder.encode.assert_called_once_with(["example 1", "example 2"], normalize=True)
        assert isinstance(result, np.ndarray)
        assert pattern.vector is result

    def test_compute_vector_max_strategy(self):
        """Test vector computation with max strategy."""
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = np.array([[0.6, 0.8, 0.0]])

        pattern = SemanticPattern(
            pattern_id="test/max",
            examples=["example"],
        )

        result = pattern.compute_vector(mock_encoder, strategy="max")

        assert isinstance(result, np.ndarray)
        assert pattern.vector is result

    def test_compute_vector_normalizes_result(self):
        """Test that computed vector is normalized to unit length."""
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = np.array([[3.0, 4.0, 0.0]])

        pattern = SemanticPattern(
            pattern_id="test/norm",
            examples=["example"],
        )

        result = pattern.compute_vector(mock_encoder)

        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 1e-6

    def test_compute_vector_stores_on_instance(self):
        """Test that computed vector is stored on the pattern instance."""
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = np.array([[1.0, 0.0, 0.0]])

        pattern = SemanticPattern(
            pattern_id="test/store",
            examples=["example"],
        )

        assert pattern.vector is None
        pattern.compute_vector(mock_encoder)
        assert pattern.vector is not None

    def test_compute_vector_no_examples_raises(self):
        """Test that computing vector with no examples raises ValueError."""
        pattern = SemanticPattern(
            pattern_id="empty/pattern",
            examples=[],
        )
        mock_encoder = MagicMock()

        with pytest.raises(
            ValueError, match="Cannot compute vector for pattern 'empty/pattern': no examples"
        ):
            pattern.compute_vector(mock_encoder)

    def test_compute_vector_unknown_strategy_raises(self):
        """Test that unknown aggregation strategy raises ValueError."""
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = np.array([[1.0, 0.0]])

        pattern = SemanticPattern(
            pattern_id="test/strategy",
            examples=["example"],
        )

        with pytest.raises(ValueError, match="Unknown aggregation strategy"):
            pattern.compute_vector(mock_encoder, strategy="median")

    def test_compute_vector_encoder_called_with_normalize(self):
        """Test that encoder.encode is called with normalize=True."""
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = np.array([[1.0, 0.0, 0.0]])

        pattern = SemanticPattern(
            pattern_id="test",
            examples=["hello"],
        )

        pattern.compute_vector(mock_encoder)

        mock_encoder.encode.assert_called_once_with(["hello"], normalize=True)


class TestSemanticMatch:
    """Tests for SemanticMatch dataclass."""

    def test_default_values(self):
        """Test default field values."""
        match = SemanticMatch(
            pattern_id="test/pattern",
            confidence=0.9,
            semantic_score=0.85,
        )

        assert match.pattern_id == "test/pattern"
        assert match.confidence == 0.9
        assert match.semantic_score == 0.85
        assert match.semantic_method == SemanticMethod.COSINE
        assert match.vector_similarity is None
        assert match.model_used is None
        assert match.encoding_time is None

    def test_custom_values(self):
        """Test custom field values."""
        match = SemanticMatch(
            pattern_id="security/scan",
            confidence=0.92,
            semantic_score=0.87,
            semantic_method=SemanticMethod.HYBRID,
            vector_similarity=0.88,
            model_used="all-MiniLM-L6-v2",
            encoding_time=0.015,
        )

        assert match.pattern_id == "security/scan"
        assert match.confidence == 0.92
        assert match.semantic_score == 0.87
        assert match.semantic_method == SemanticMethod.HYBRID
        assert match.vector_similarity == 0.88
        assert match.model_used == "all-MiniLM-L6-v2"
        assert match.encoding_time == 0.015

    def test_semantic_method_as_string(self):
        """Test semantic_method can be a plain string."""
        match = SemanticMatch(
            pattern_id="test",
            confidence=0.8,
            semantic_score=0.75,
            semantic_method="cosine",
        )

        assert match.semantic_method == "cosine"

    def test_to_dict_basic(self):
        """Test to_dict returns correct dictionary."""
        match = SemanticMatch(
            pattern_id="test/pattern",
            confidence=0.9,
            semantic_score=0.85,
        )

        result = match.to_dict()

        assert result == {
            "pattern_id": "test/pattern",
            "confidence": 0.9,
            "semantic_score": 0.85,
            "semantic_method": "SemanticMethod.COSINE",
            "vector_similarity": None,
            "model_used": None,
            "encoding_time": None,
        }

    def test_to_dict_with_all_fields(self):
        """Test to_dict includes all fields when set."""
        match = SemanticMatch(
            pattern_id="test/full",
            confidence=0.95,
            semantic_score=0.9,
            semantic_method=SemanticMethod.HYBRID,
            vector_similarity=0.91,
            model_used="paraphrase-multilingual-MiniLM-L12-v2",
            encoding_time=0.012,
        )

        result = match.to_dict()

        assert result["pattern_id"] == "test/full"
        assert result["confidence"] == 0.95
        assert result["semantic_score"] == 0.9
        assert result["semantic_method"] == "SemanticMethod.HYBRID"
        assert result["vector_similarity"] == 0.91
        assert result["model_used"] == "paraphrase-multilingual-MiniLM-L12-v2"
        assert result["encoding_time"] == 0.012

    def test_to_dict_with_string_method(self):
        """Test to_dict with semantic_method as plain string."""
        match = SemanticMatch(
            pattern_id="test",
            confidence=0.8,
            semantic_score=0.75,
            semantic_method="custom_method",
        )

        result = match.to_dict()

        assert result["semantic_method"] == "custom_method"

    def test_to_dict_returns_new_dict(self):
        """Test that to_dict returns a new dict each time."""
        match = SemanticMatch(
            pattern_id="test",
            confidence=0.8,
            semantic_score=0.75,
        )

        d1 = match.to_dict()
        d2 = match.to_dict()

        assert d1 == d2
        assert d1 is not d2


class TestEncoderConfig:
    """Tests for EncoderConfig Pydantic model."""

    def test_default_values(self):
        """Test default field values."""
        config = EncoderConfig()

        assert config.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
        assert config.device == "auto"
        assert config.cache_dir is None
        assert config.batch_size == 32
        assert config.show_progress is False
        assert config.enable_half_precision is True
        assert config.enable_model_cache is True

    def test_custom_values(self):
        """Test custom field values."""
        config = EncoderConfig(
            model_name="all-MiniLM-L6-v2",
            device="cuda",
            cache_dir=Path("/tmp/cache"),
            batch_size=64,
            show_progress=True,
            enable_half_precision=False,
            enable_model_cache=False,
        )

        assert config.model_name == "all-MiniLM-L6-v2"
        assert config.device == "cuda"
        assert config.cache_dir == Path("/tmp/cache")
        assert config.batch_size == 64
        assert config.show_progress is True
        assert config.enable_half_precision is False
        assert config.enable_model_cache is False

    def test_batch_size_validation_min(self):
        """Test batch_size minimum validation."""
        with pytest.raises(Exception):
            EncoderConfig(batch_size=0)

    def test_batch_size_validation_max(self):
        """Test batch_size maximum validation."""
        with pytest.raises(Exception):
            EncoderConfig(batch_size=257)

    def test_batch_size_boundary_values(self):
        """Test batch_size at boundary values."""
        config_min = EncoderConfig(batch_size=1)
        config_max = EncoderConfig(batch_size=256)

        assert config_min.batch_size == 1
        assert config_max.batch_size == 256

    def test_device_literal_values(self):
        """Test valid device values."""
        for device in ["auto", "cpu", "cuda", "mps"]:
            config = EncoderConfig(device=device)
            assert config.device == device

    def test_to_dict(self):
        """Test to_dict returns correct dictionary."""
        config = EncoderConfig(
            model_name="test-model",
            device="cpu",
            batch_size=16,
        )

        result = config.to_dict()

        assert isinstance(result, dict)
        assert result["model_name"] == "test-model"
        assert result["device"] == "cpu"
        assert result["batch_size"] == 16

    def test_from_dict(self):
        """Test from_dict class method."""
        config = EncoderConfig.from_dict(
            {
                "model_name": "custom-model",
                "device": "mps",
                "batch_size": 8,
            }
        )

        assert config.model_name == "custom-model"
        assert config.device == "mps"
        assert config.batch_size == 8

    def test_from_dict_partial(self):
        """Test from_dict with partial config uses defaults."""
        config = EncoderConfig.from_dict({"model_name": "only-model"})

        assert config.model_name == "only-model"
        assert config.device == "auto"
        assert config.batch_size == 32

    def test_from_dict_empty(self):
        """Test from_dict with empty dict uses all defaults."""
        config = EncoderConfig.from_dict({})

        assert config.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
        assert config.device == "auto"

    def test_from_env_all_set(self):
        """Test from_env with all environment variables set."""
        env = {
            "VIBE_SEMANTIC_MODEL": "custom-model",
            "VIBE_SEMANTIC_DEVICE": "cuda",
            "VIBE_SEMANTIC_CACHE_DIR": "/tmp/models",
            "VIBE_SEMANTIC_BATCH_SIZE": "16",
            "VIBE_SEMANTIC_SHOW_PROGRESS": "true",
            "VIBE_SEMANTIC_HALF_PRECISION": "false",
            "VIBE_SEMANTIC_MODEL_CACHE": "false",
        }

        with patch.dict(os.environ, env, clear=False):
            config = EncoderConfig.from_env()

        assert config.model_name == "custom-model"
        assert config.device == "cuda"
        assert config.cache_dir == Path("/tmp/models")
        assert config.batch_size == 16
        assert config.show_progress is True
        assert config.enable_half_precision is False
        assert config.enable_model_cache is False

    def test_from_env_none_set(self):
        """Test from_env with no environment variables uses defaults."""
        env_keys = [
            "VIBE_SEMANTIC_MODEL",
            "VIBE_SEMANTIC_DEVICE",
            "VIBE_SEMANTIC_CACHE_DIR",
            "VIBE_SEMANTIC_BATCH_SIZE",
            "VIBE_SEMANTIC_SHOW_PROGRESS",
            "VIBE_SEMANTIC_HALF_PRECISION",
            "VIBE_SEMANTIC_MODEL_CACHE",
        ]

        original = {}
        for key in env_keys:
            original[key] = os.environ.pop(key, None)

        try:
            config = EncoderConfig.from_env()

            assert config.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
            assert config.device == "auto"
            assert config.cache_dir == Path(".")
            assert config.batch_size == 32
            assert config.show_progress is False
            assert config.enable_half_precision is True
            assert config.enable_model_cache is True
        finally:
            for key, value in original.items():
                if value is not None:
                    os.environ[key] = value

    def test_from_env_partial(self):
        """Test from_env with only some environment variables set."""
        with patch.dict(os.environ, {"VIBE_SEMANTIC_MODEL": "partial-model"}):
            config = EncoderConfig.from_env()

        assert config.model_name == "partial-model"
        assert config.device == "auto"
        assert config.batch_size == 32

    def test_from_env_show_progress_case_insensitive(self):
        """Test that VIBE_SEMANTIC_SHOW_PROGRESS is case insensitive."""
        with patch.dict(os.environ, {"VIBE_SEMANTIC_SHOW_PROGRESS": "TRUE"}):
            config = EncoderConfig.from_env()

        assert config.show_progress is True

    def test_from_env_half_precision_case_insensitive(self):
        """Test that VIBE_SEMANTIC_HALF_PRECISION is case insensitive."""
        with patch.dict(os.environ, {"VIBE_SEMANTIC_HALF_PRECISION": "FALSE"}):
            config = EncoderConfig.from_env()

        assert config.enable_half_precision is False

    def test_from_env_cache_dir_empty_string(self):
        """Test from_env with empty cache dir env var."""
        with patch.dict(os.environ, {"VIBE_SEMANTIC_CACHE_DIR": ""}):
            config = EncoderConfig.from_env()

        assert config.cache_dir == Path(".")


class TestSemanticConfig:
    """Tests for SemanticConfig Pydantic model."""

    def test_default_values(self):
        """Test default field values."""
        config = SemanticConfig()

        assert config.enabled is False
        assert isinstance(config.encoder, EncoderConfig)
        assert config.strategy == "hybrid"
        assert config.keyword_weight == 0.3
        assert config.regex_weight == 0.2
        assert config.semantic_weight == 0.5
        assert config.threshold == 0.7

    def test_custom_values(self):
        """Test custom field values."""
        config = SemanticConfig(
            enabled=True,
            strategy="cosine",
            keyword_weight=0.2,
            regex_weight=0.3,
            semantic_weight=0.5,
            threshold=0.85,
        )

        assert config.enabled is True
        assert config.strategy == "cosine"
        assert config.keyword_weight == 0.2
        assert config.regex_weight == 0.3
        assert config.semantic_weight == 0.5
        assert config.threshold == 0.85

    def test_encoder_default_factory(self):
        """Test that encoder is created with default factory."""
        config1 = SemanticConfig()
        config2 = SemanticConfig()

        assert config1.encoder is not config2.encoder
        assert config1.encoder.model_name == config2.encoder.model_name

    def test_encoder_custom(self):
        """Test with custom encoder config."""
        encoder = EncoderConfig(model_name="custom", device="cuda")
        config = SemanticConfig(encoder=encoder)

        assert config.encoder.model_name == "custom"
        assert config.encoder.device == "cuda"

    def test_weight_validation_hybrid_valid(self):
        """Test validate_weights with valid hybrid weights."""
        config = SemanticConfig(
            strategy="hybrid",
            keyword_weight=0.3,
            regex_weight=0.2,
            semantic_weight=0.5,
        )

        config.validate_weights()

    def test_weight_validation_hybrid_invalid(self):
        """Test validate_weights with invalid hybrid weights."""
        config = SemanticConfig(
            strategy="hybrid",
            keyword_weight=0.5,
            regex_weight=0.5,
            semantic_weight=0.5,
        )

        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            config.validate_weights()

    def test_weight_validation_cosine_skips(self):
        """Test validate_weights skips validation for cosine strategy."""
        config = SemanticConfig(
            strategy="cosine",
            keyword_weight=0.9,
            regex_weight=0.9,
            semantic_weight=0.9,
        )

        config.validate_weights()

    def test_weight_validation_near_one_tolerance(self):
        """Test validate_weights with weights within tolerance of 1.0."""
        config = SemanticConfig(
            strategy="hybrid",
            keyword_weight=0.33,
            regex_weight=0.33,
            semantic_weight=0.34,
        )

        config.validate_weights()

    def test_weight_validation_outside_tolerance(self):
        """Test validate_weights with weights outside tolerance."""
        config = SemanticConfig(
            strategy="hybrid",
            keyword_weight=0.1,
            regex_weight=0.1,
            semantic_weight=0.1,
        )

        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            config.validate_weights()

    def test_keyword_weight_boundary_min(self):
        """Test keyword_weight minimum boundary."""
        config = SemanticConfig(keyword_weight=0.0)
        assert config.keyword_weight == 0.0

    def test_keyword_weight_boundary_max(self):
        """Test keyword_weight maximum boundary."""
        config = SemanticConfig(keyword_weight=1.0)
        assert config.keyword_weight == 1.0

    def test_keyword_weight_below_min_raises(self):
        """Test keyword_weight below minimum raises validation error."""
        with pytest.raises(Exception):
            SemanticConfig(keyword_weight=-0.1)

    def test_keyword_weight_above_max_raises(self):
        """Test keyword_weight above maximum raises validation error."""
        with pytest.raises(Exception):
            SemanticConfig(keyword_weight=1.1)

    def test_regex_weight_boundaries(self):
        """Test regex_weight boundaries."""
        config_min = SemanticConfig(regex_weight=0.0)
        config_max = SemanticConfig(regex_weight=1.0)

        assert config_min.regex_weight == 0.0
        assert config_max.regex_weight == 1.0

    def test_semantic_weight_boundaries(self):
        """Test semantic_weight boundaries."""
        config_min = SemanticConfig(semantic_weight=0.0)
        config_max = SemanticConfig(semantic_weight=1.0)

        assert config_min.semantic_weight == 0.0
        assert config_max.semantic_weight == 1.0

    def test_threshold_boundaries(self):
        """Test threshold boundaries."""
        config_min = SemanticConfig(threshold=0.0)
        config_max = SemanticConfig(threshold=1.0)

        assert config_min.threshold == 0.0
        assert config_max.threshold == 1.0

    def test_from_env_all_set(self):
        """Test from_env with all environment variables set."""
        env = {
            "VIBE_SEMANTIC_ENABLED": "true",
            "VIBE_SEMANTIC_STRATEGY": "cosine",
            "VIBE_SEMANTIC_KEYWORD_WEIGHT": "0.25",
            "VIBE_SEMANTIC_REGEX_WEIGHT": "0.25",
            "VIBE_SEMANTIC_SEMANTIC_WEIGHT": "0.5",
            "VIBE_SEMANTIC_THRESHOLD": "0.8",
            "VIBE_SEMANTIC_MODEL": "env-model",
        }

        with patch.dict(os.environ, env, clear=False):
            config = SemanticConfig.from_env()

        assert config.enabled is True
        assert config.strategy == "cosine"
        assert config.keyword_weight == 0.25
        assert config.regex_weight == 0.25
        assert config.semantic_weight == 0.5
        assert config.threshold == 0.8
        assert config.encoder.model_name == "env-model"

    def test_from_env_none_set(self):
        """Test from_env with no environment variables uses defaults."""
        env_keys = [
            "VIBE_SEMANTIC_ENABLED",
            "VIBE_SEMANTIC_STRATEGY",
            "VIBE_SEMANTIC_KEYWORD_WEIGHT",
            "VIBE_SEMANTIC_REGEX_WEIGHT",
            "VIBE_SEMANTIC_SEMANTIC_WEIGHT",
            "VIBE_SEMANTIC_THRESHOLD",
            "VIBE_SEMANTIC_MODEL",
            "VIBE_SEMANTIC_DEVICE",
            "VIBE_SEMANTIC_CACHE_DIR",
            "VIBE_SEMANTIC_BATCH_SIZE",
            "VIBE_SEMANTIC_SHOW_PROGRESS",
            "VIBE_SEMANTIC_HALF_PRECISION",
            "VIBE_SEMANTIC_MODEL_CACHE",
        ]

        original = {}
        for key in env_keys:
            original[key] = os.environ.pop(key, None)

        try:
            config = SemanticConfig.from_env()

            assert config.enabled is False
            assert config.strategy == "hybrid"
            assert config.keyword_weight == 0.3
            assert config.regex_weight == 0.2
            assert config.semantic_weight == 0.5
            assert config.threshold == 0.7
        finally:
            for key, value in original.items():
                if value is not None:
                    os.environ[key] = value

    def test_from_env_enabled_case_insensitive(self):
        """Test that VIBE_SEMANTIC_ENABLED is case insensitive."""
        with patch.dict(os.environ, {"VIBE_SEMANTIC_ENABLED": "TRUE"}):
            config = SemanticConfig.from_env()

        assert config.enabled is True

    def test_from_env_disabled(self):
        """Test from_env with disabled setting."""
        with patch.dict(os.environ, {"VIBE_SEMANTIC_ENABLED": "false"}):
            config = SemanticConfig.from_env()

        assert config.enabled is False

    def test_from_env_partial(self):
        """Test from_env with only some environment variables."""
        with patch.dict(
            os.environ,
            {
                "VIBE_SEMANTIC_ENABLED": "true",
                "VIBE_SEMANTIC_THRESHOLD": "0.9",
            },
        ):
            config = SemanticConfig.from_env()

        assert config.enabled is True
        assert config.threshold == 0.9
        assert config.strategy == "hybrid"
