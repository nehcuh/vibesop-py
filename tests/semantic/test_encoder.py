"""Unit tests for semantic encoder."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("numpy", reason="numpy not installed")
pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")

import numpy as np

from vibesop.semantic.encoder import SemanticEncoder


class TestSemanticEncoderInit:
    """Tests for SemanticEncoder initialization."""

    def test_initialization_default(self):
        """Test encoder initialization with default parameters."""
        encoder = SemanticEncoder()

        assert encoder.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
        assert encoder._device == "auto"
        assert encoder.batch_size == 32
        assert encoder.show_progress is False
        assert encoder._model is None  # Model not loaded yet

    def test_initialization_custom_model(self):
        """Test encoder initialization with custom model."""
        encoder = SemanticEncoder(model_name="all-MiniLM-L6-v2")

        assert encoder.model_name == "all-MiniLM-L6-v2"

    def test_initialization_custom_device(self):
        """Test encoder initialization with custom device."""
        encoder = SemanticEncoder(device="cpu")

        assert encoder._device == "cpu"

    def test_initialization_custom_batch_size(self):
        """Test encoder initialization with custom batch size."""
        encoder = SemanticEncoder(batch_size=64)

        assert encoder.batch_size == 64


class TestSemanticEncoderEncode:
    """Tests for SemanticEncoder.encode() method."""

    def test_encode_single_text(self):
        """Test encoding a single text string."""
        encoder = SemanticEncoder()

        vector = encoder.encode("Hello world")

        assert isinstance(vector, np.ndarray)
        assert vector.ndim == 1
        assert len(vector) == 384  # MiniLM-L12-v2 dimension
        assert np.all((vector >= -1) & (vector <= 1))  # Normalized

    def test_encode_list_of_texts(self):
        """Test encoding a list of texts."""
        encoder = SemanticEncoder()

        texts = ["Hello world", "Goodbye world", "Test text"]
        vectors = encoder.encode(texts)

        assert isinstance(vectors, np.ndarray)
        assert vectors.ndim == 2
        assert vectors.shape == (3, 384)

    def test_encode_empty_string(self):
        """Test encoding an empty string."""
        encoder = SemanticEncoder()

        # Empty string should work
        vector = encoder.encode("")
        assert vector.shape == (384,)

    def test_encode_normalize_true(self):
        """Test encoding with normalization enabled."""
        encoder = SemanticEncoder()

        vector = encoder.encode("test text", normalize=True)

        # Check if normalized (L2 norm ≈ 1)
        norm = np.linalg.norm(vector)
        assert abs(norm - 1.0) < 1e-5

    def test_encode_normalize_false(self):
        """Test encoding with normalization disabled."""
        encoder = SemanticEncoder()

        vector = encoder.encode("test text", normalize=False)

        # Without normalization, L2 norm may not be 1
        # But it should still be a valid vector
        assert len(vector) == 384

    def test_encode_batch_size(self):
        """Test encoding with custom batch size."""
        encoder = SemanticEncoder()

        texts = ["text"] * 100
        vectors = encoder.encode(texts, batch_size=10)

        assert vectors.shape == (100, 384)

    def test_encode_single_input_returns_1d(self):
        """Test that single string input returns 1D array."""
        encoder = SemanticEncoder()

        vector = encoder.encode("test")

        assert vector.ndim == 1
        assert vector.shape == (384,)

    def test_encode_list_input_returns_2d(self):
        """Test that list input returns 2D array."""
        encoder = SemanticEncoder()

        vectors = encoder.encode(["test1", "test2"])

        assert vectors.ndim == 2
        assert vectors.shape == (2, 384)


class TestSemanticEncoderEncodeQuery:
    """Tests for SemanticEncoder.encode_query() method."""

    def test_encode_query_single(self):
        """Test encoding a single query."""
        encoder = SemanticEncoder()

        vector = encoder.encode_query("scan for vulnerabilities")

        assert isinstance(vector, np.ndarray)
        assert vector.ndim == 1
        assert len(vector) == 384

    def test_encode_query_normalized(self):
        """Test that query vectors are normalized by default."""
        encoder = SemanticEncoder()

        vector = encoder.encode_query("test query")

        norm = np.linalg.norm(vector)
        assert abs(norm - 1.0) < 1e-5

    def test_encode_query_not_normalized(self):
        """Test encoding query without normalization."""
        encoder = SemanticEncoder()

        vector = encoder.encode_query("test query", normalize=False)

        # Without normalization, just check it's a valid vector
        assert len(vector) == 384


class TestSemanticEncoderDimension:
    """Tests for SemanticEncoder.get_dimension() method."""

    def test_get_dimension_before_model_load(self):
        """Test getting dimension before model is loaded."""
        encoder = SemanticEncoder()

        # Should load model and return dimension
        dim = encoder.get_dimension()

        assert dim == 384
        assert encoder._model is not None  # Model should be loaded now

    def test_get_dimension_after_encode(self):
        """Test getting dimension after encoding."""
        encoder = SemanticEncoder()

        # Encode something (this loads the model)
        encoder.encode("test")

        dim = encoder.get_dimension()
        assert dim == 384


class TestSemanticEncoderModelInfo:
    """Tests for SemanticEncoder.get_model_info() method."""

    def test_get_model_info(self):
        """Test getting model information."""
        encoder = SemanticEncoder()

        # Trigger model loading
        encoder.encode("test")

        info = encoder.get_model_info()

        assert "model_name" in info
        assert "dimension" in info
        assert "device" in info
        assert info["model_name"] == "paraphrase-multilingual-MiniLM-L12-v2"
        assert info["dimension"] == 384
        assert info["device"] in ["cpu", "cuda", "mps"]


class TestSemanticEncoderWarmup:
    """Tests for SemanticEncoder.warmup() method."""

    def test_warmup_loads_model(self):
        """Test that warmup loads the model."""
        encoder = SemanticEncoder()

        assert encoder._model is None

        encoder.warmup()

        assert encoder._model is not None

    def test_warmup_performs_encoding(self):
        """Test that warmup performs a dummy encoding."""
        encoder = SemanticEncoder()

        # Warmup should not raise any errors
        encoder.warmup()

        # Model should be loaded
        assert encoder._model is not None


class TestSemanticEncoderCache:
    """Tests for model caching functionality."""

    def test_model_caching_single_instance(self):
        """Test that multiple encoders with same model share instance."""
        encoder1 = SemanticEncoder()
        encoder2 = SemanticEncoder()

        # Load models
        encoder1.encode("test")
        encoder2.encode("test")

        # Should be the same instance (from class-level cache)
        assert encoder1._model is encoder2._model

    def test_get_cached_models(self):
        """Test getting list of cached models."""
        SemanticEncoder.clear_cache()

        encoder = SemanticEncoder()
        encoder.encode("test")

        cached = SemanticEncoder.get_cached_models()

        assert len(cached) == 1
        assert encoder.model_name in cached

    def test_clear_cache(self):
        """Test clearing model cache."""
        encoder = SemanticEncoder()
        encoder.encode("test")

        assert len(SemanticEncoder.get_cached_models()) > 0

        SemanticEncoder.clear_cache()

        assert len(SemanticEncoder.get_cached_models()) == 0


class TestSemanticEncoderErrors:
    """Tests for error handling."""

    def test_encode_empty_list_raises_error(self):
        """Test that encoding empty list raises ValueError."""
        encoder = SemanticEncoder()

        with pytest.raises(ValueError, match="texts cannot be empty"):
            encoder.encode([])

    def test_encode_invalid_device_raises_error(self):
        """Test that invalid device raises ValueError."""
        with pytest.raises(ValueError, match="Unknown device"):
            SemanticEncoder(device="invalid_device")


class TestSemanticEncoderPerformance:
    """Performance tests for SemanticEncoder."""

    @pytest.mark.slow
    def test_encode_performance(self):
        """Test encoding performance benchmark."""
        encoder = SemanticEncoder()

        import time

        texts = ["test query"] * 100

        start = time.time()
        vectors = encoder.encode(texts, batch_size=32)
        elapsed = time.time() - start

        throughput = len(texts) / elapsed

        # Should be able to encode at least 100 texts/sec
        assert throughput >= 100, f"Encoding too slow: {throughput:.0f} texts/sec"

    @pytest.mark.slow
    def test_encode_query_performance(self):
        """Test single query encoding performance."""
        encoder = SemanticEncoder()
        encoder.warmup()  # Pre-load model

        import time

        iterations = 100
        start = time.time()

        for _ in range(iterations):
            encoder.encode_query("test query")

        elapsed = time.time() - start
        avg_time = elapsed / iterations

        # Should be less than 10ms per query
        assert avg_time < 0.01, f"Query encoding too slow: {avg_time * 1000:.2f}ms"


class TestSemanticEncoderMultilingual:
    """Tests for multilingual encoding."""

    def test_encode_english(self):
        """Test encoding English text."""
        encoder = SemanticEncoder()

        vector = encoder.encode("Hello world")

        assert vector.shape == (384,)

    def test_encode_chinese(self):
        """Test encoding Chinese text."""
        encoder = SemanticEncoder()

        vector = encoder.encode("你好世界")

        assert vector.shape == (384,)

    def test_encode_mixed_language(self):
        """Test encoding mixed language text."""
        encoder = SemanticEncoder()

        vector = encoder.encode("Hello 你好 world 世界")

        assert vector.shape == (384,)

    def test_encode_mixed_language_list(self):
        """Test encoding list of mixed language texts."""
        encoder = SemanticEncoder()

        texts = [
            "Hello world",
            "你好世界",
            "scan for vulnerabilities",
            "扫描安全漏洞",
        ]
        vectors = encoder.encode(texts)

        assert vectors.shape == (4, 384)

        # All vectors should be normalized
        norms = np.linalg.norm(vectors, axis=1)
        assert np.all(np.abs(norms - 1.0) < 1e-5)
