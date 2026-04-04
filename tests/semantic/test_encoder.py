"""Comprehensive unit tests for SemanticEncoder with mocked models.

All tests mock sentence_transformers.SentenceTransformer to avoid
loading real models. Tests cover all public methods and key private methods.
"""

# pyright: reportPrivateUsage=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none, reportUnknownParameterType=none, reportMissingParameterType=none

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture
def mock_st_module():
    """Mock the entire sentence_transformers module."""
    mock_module = MagicMock()
    mock_model_instance = MagicMock()
    mock_model_instance.get_sentence_embedding_dimension.return_value = 384
    mock_model_instance.max_seq_length = 128
    mock_model_instance.encode.return_value = np.random.rand(384).astype(np.float32)
    mock_module.SentenceTransformer.return_value = mock_model_instance
    with patch.dict(sys.modules, {"sentence_transformers": mock_module}):
        yield mock_module


@pytest.fixture
def mock_torch():
    """Mock torch for device detection tests."""
    mock = MagicMock()
    mock.cuda.is_available.return_value = False
    mock.backends.mps.is_available.return_value = False
    with patch.dict(sys.modules, {"torch": mock}):
        yield mock


@pytest.fixture(autouse=True)
def clear_model_cache():
    """Clear the class-level model cache before each test."""
    from vibesop.semantic.encoder import SemanticEncoder

    SemanticEncoder._model_cache.clear()
    yield
    SemanticEncoder._model_cache.clear()


class TestSemanticEncoderInit:
    """Tests for SemanticEncoder.__init__."""

    def test_init_default_params(self, mock_st_module):
        """Test initialization with default parameters."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()

        assert encoder.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
        assert encoder._device == "auto"
        assert encoder._cache_dir is None
        assert encoder.batch_size == 32
        assert encoder.show_progress is False
        assert encoder._model is None
        assert encoder._dimension is None

    def test_init_custom_params(self, mock_st_module):
        """Test initialization with custom parameters."""
        from vibesop.semantic.encoder import SemanticEncoder

        cache_dir = Path("/tmp/cache")
        encoder = SemanticEncoder(
            model_name="all-MiniLM-L6-v2",
            device="cpu",
            cache_dir=cache_dir,
            batch_size=64,
            show_progress=True,
        )

        assert encoder.model_name == "all-MiniLM-L6-v2"
        assert encoder._device == "cpu"
        assert encoder._cache_dir == cache_dir
        assert encoder.batch_size == 64
        assert encoder.show_progress is True

    def test_init_does_not_load_model(self, mock_st_module):
        """Test that __init__ does not trigger model loading."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()

        mock_st_module.SentenceTransformer.assert_not_called()
        assert encoder._model is None

    def test_init_raises_import_error_when_sentence_transformers_missing(self):
        """Test ImportError when sentence-transformers is not installed."""
        original = sys.modules.get("sentence_transformers")
        if "sentence_transformers" in sys.modules:
            del sys.modules["sentence_transformers"]

        try:
            if "vibesop.semantic.encoder" in sys.modules:
                del sys.modules["vibesop.semantic.encoder"]

            with patch.dict(sys.modules, {"sentence_transformers": None}):
                from vibesop.semantic.encoder import SemanticEncoder

                with pytest.raises(ImportError, match="sentence-transformers is required"):
                    SemanticEncoder()
        finally:
            if original is not None:
                sys.modules["sentence_transformers"] = original
            if "vibesop.semantic.encoder" in sys.modules:
                del sys.modules["vibesop.semantic.encoder"]


class TestLoadModel:
    """Tests for SemanticEncoder._load_model."""

    def test_load_model_calls_sentence_transformer(self, mock_st_module, mock_torch):
        """Test that _load_model calls SentenceTransformer."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        model = encoder._load_model()

        mock_st_module.SentenceTransformer.assert_called_once()
        assert model is mock_st_module.SentenceTransformer.return_value

    def test_load_model_passes_device(self, mock_st_module, mock_torch):
        """Test that _load_model passes correct device."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder(device="cpu")
        encoder._load_model()

        call_kwargs = mock_st_module.SentenceTransformer.call_args
        assert call_kwargs.kwargs["device"] == "cpu"

    def test_load_model_passes_cache_folder(self, mock_st_module, mock_torch):
        """Test that _load_model passes cache_folder when set."""
        from vibesop.semantic.encoder import SemanticEncoder

        cache_dir = Path("/tmp/models")
        encoder = SemanticEncoder(cache_dir=cache_dir)
        encoder._load_model()

        call_kwargs = mock_st_module.SentenceTransformer.call_args
        assert call_kwargs.kwargs["cache_folder"] == str(cache_dir)

    def test_load_model_no_cache_folder_when_none(self, mock_st_module, mock_torch):
        """Test that cache_folder is not passed when cache_dir is None."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder._load_model()

        call_kwargs = mock_st_module.SentenceTransformer.call_args
        assert "cache_folder" not in call_kwargs.kwargs

    def test_load_model_caches_result(self, mock_st_module, mock_torch):
        """Test that loaded model is stored in class cache."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder._load_model()

        assert encoder.model_name in SemanticEncoder._model_cache

    def test_load_model_sets_dimension(self, mock_st_module, mock_torch):
        """Test that _load_model sets _dimension from model."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder._load_model()

        assert encoder._dimension == 384

    def test_load_model_uses_cache(self, mock_st_module, mock_torch):
        """Test that _load_model returns cached model on second call."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder1 = SemanticEncoder()
        encoder2 = SemanticEncoder()

        model1 = encoder1._load_model()
        mock_st_module.SentenceTransformer.reset_mock()
        model2 = encoder2._load_model()

        assert model1 is model2
        mock_st_module.SentenceTransformer.assert_not_called()

    def test_load_model_different_models_not_shared(self, mock_st_module, mock_torch):
        """Test that different model names get separate cache entries."""
        from vibesop.semantic.encoder import SemanticEncoder

        mock_st_module.SentenceTransformer.reset_mock()
        encoder1 = SemanticEncoder(model_name="model-a")
        encoder2 = SemanticEncoder(model_name="model-b")

        encoder1._load_model()
        encoder2._load_model()

        assert mock_st_module.SentenceTransformer.call_count == 2
        assert len(SemanticEncoder._model_cache) == 2


class TestGetDevice:
    """Tests for SemanticEncoder._get_device."""

    def test_get_device_explicit_cpu(self, mock_st_module):
        """Test explicit cpu device."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder(device="cpu")
        assert encoder._get_device() == "cpu"

    def test_get_device_explicit_cuda(self, mock_st_module):
        """Test explicit cuda device."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder(device="cuda")
        assert encoder._get_device() == "cuda"

    def test_get_device_explicit_mps(self, mock_st_module):
        """Test explicit mps device."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder(device="mps")
        assert encoder._get_device() == "mps"

    def test_get_device_auto_returns_cpu_when_no_gpu(self, mock_st_module, mock_torch):
        """Test auto-detection returns cpu when no GPU available."""
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = False

        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder(device="auto")
        assert encoder._get_device() == "cpu"

    def test_get_device_auto_returns_cuda_when_available(self, mock_st_module):
        """Test auto-detection returns cuda when available."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        with patch.dict(sys.modules, {"torch": mock_torch}):
            from vibesop.semantic.encoder import SemanticEncoder

            encoder = SemanticEncoder(device="auto")
            assert encoder._get_device() == "cuda"

    def test_get_device_auto_returns_mps_when_available(self, mock_st_module):
        """Test auto-detection returns mps when available (Apple Silicon)."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = True
        with patch.dict(sys.modules, {"torch": mock_torch}):
            from vibesop.semantic.encoder import SemanticEncoder

            encoder = SemanticEncoder(device="auto")
            assert encoder._get_device() == "mps"

    def test_get_device_returns_cpu_when_torch_missing(self, mock_st_module):
        """Test auto-detection returns cpu when torch is not installed."""
        original_torch = sys.modules.get("torch")
        if "torch" in sys.modules:
            del sys.modules["torch"]

        try:
            from vibesop.semantic.encoder import SemanticEncoder

            encoder = SemanticEncoder(device="auto")
            assert encoder._get_device() == "cpu"
        finally:
            if original_torch is not None:
                sys.modules["torch"] = original_torch


class TestModelProperty:
    """Tests for SemanticEncoder.model property."""

    def test_model_property_loads_on_first_access(self, mock_st_module, mock_torch):
        """Test that model property triggers lazy loading."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        assert encoder._model is None

        _ = encoder.model

        assert encoder._model is not None
        mock_st_module.SentenceTransformer.assert_called_once()

    def test_model_property_returns_cached_on_second_access(self, mock_st_module, mock_torch):
        """Test that model property returns cached model."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        _ = encoder.model
        mock_st_module.SentenceTransformer.reset_mock()

        _ = encoder.model

        mock_st_module.SentenceTransformer.assert_not_called()


class TestEncode:
    """Tests for SemanticEncoder.encode."""

    def test_encode_single_text(self, mock_st_module, mock_torch):
        """Test encoding a single text string."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [[0.1] * 384], dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        vector = encoder.encode("hello world")

        assert isinstance(vector, np.ndarray)
        assert vector.ndim == 1
        assert vector.shape == (384,)

    def test_encode_list_of_texts(self, mock_st_module, mock_torch):
        """Test encoding a list of texts."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [[0.1] * 384, [0.2] * 384], dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        vectors = encoder.encode(["hello", "world"])

        assert isinstance(vectors, np.ndarray)
        assert vectors.ndim == 2
        assert vectors.shape == (2, 384)

    def test_encode_passes_batch_size(self, mock_st_module, mock_torch):
        """Test that encode passes batch_size to model."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [0.1] * 384, dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder(batch_size=16)
        encoder.encode("test")

        call_kwargs = mock_st_module.SentenceTransformer.return_value.encode.call_args
        assert call_kwargs.kwargs["batch_size"] == 16

    def test_encode_override_batch_size(self, mock_st_module, mock_torch):
        """Test that encode can override batch_size."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [0.1] * 384, dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder(batch_size=16)
        encoder.encode("test", batch_size=8)

        call_kwargs = mock_st_module.SentenceTransformer.return_value.encode.call_args
        assert call_kwargs.kwargs["batch_size"] == 8

    def test_encode_passes_normalize(self, mock_st_module, mock_torch):
        """Test that encode passes normalize_embeddings."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [0.1] * 384, dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder.encode("test", normalize=True)

        call_kwargs = mock_st_module.SentenceTransformer.return_value.encode.call_args
        assert call_kwargs.kwargs["normalize_embeddings"] is True

    def test_encode_passes_show_progress(self, mock_st_module, mock_torch):
        """Test that encode passes show_progress_bar."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [0.1] * 384, dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder(show_progress=True)
        encoder.encode("test")

        call_kwargs = mock_st_module.SentenceTransformer.return_value.encode.call_args
        assert call_kwargs.kwargs["show_progress_bar"] is True

    def test_encode_override_show_progress(self, mock_st_module, mock_torch):
        """Test that encode can override show_progress."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [0.1] * 384, dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder(show_progress=True)
        encoder.encode("test", show_progress=False)

        call_kwargs = mock_st_module.SentenceTransformer.return_value.encode.call_args
        assert call_kwargs.kwargs["show_progress_bar"] is False

    def test_encode_empty_list_raises_value_error(self, mock_st_module):
        """Test that encoding empty list raises ValueError."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()

        with pytest.raises(ValueError, match="texts cannot be empty"):
            encoder.encode([])

    def test_encode_empty_string_raises_value_error(self, mock_st_module):
        """Test that encoding empty string raises ValueError (falsy check)."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()

        with pytest.raises(ValueError, match="texts cannot be empty"):
            encoder.encode("")

    def test_encode_triggers_model_loading(self, mock_st_module, mock_torch):
        """Test that encode triggers lazy model loading."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [0.1] * 384, dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        assert encoder._model is None

        encoder.encode("test")

        mock_st_module.SentenceTransformer.assert_called_once()
        assert encoder._model is not None

    def test_encode_single_input_returns_1d(self, mock_st_module, mock_torch):
        """Test that single string input returns 1D array."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [[0.1] * 384], dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        vector = encoder.encode("test")

        assert vector.ndim == 1

    def test_encode_list_input_returns_2d(self, mock_st_module, mock_torch):
        """Test that list input returns 2D array."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [[0.1] * 384, [0.2] * 384], dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        vectors = encoder.encode(["a", "b"])

        assert vectors.ndim == 2

    def test_encode_large_batch(self, mock_st_module, mock_torch):
        """Test encoding a large batch of texts."""
        texts = [f"text {i}" for i in range(100)]
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [[0.1] * 384] * 100, dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        vectors = encoder.encode(texts, batch_size=32)

        assert vectors.shape == (100, 384)


class TestEncodeQuery:
    """Tests for SemanticEncoder.encode_query."""

    def test_encode_query_returns_1d_vector(self, mock_st_module, mock_torch):
        """Test that encode_query returns a 1D vector."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [[0.1] * 384], dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        vector = encoder.encode_query("test query")

        assert vector.ndim == 1
        assert vector.shape == (384,)

    def test_encode_query_passes_normalize_true(self, mock_st_module, mock_torch):
        """Test that encode_query passes normalize=True by default."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [0.1] * 384, dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder.encode_query("test")

        call_kwargs = mock_st_module.SentenceTransformer.return_value.encode.call_args
        assert call_kwargs.kwargs["normalize_embeddings"] is True

    def test_encode_query_passes_normalize_false(self, mock_st_module, mock_torch):
        """Test that encode_query can disable normalization."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [0.1] * 384, dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder.encode_query("test", normalize=False)

        call_kwargs = mock_st_module.SentenceTransformer.return_value.encode.call_args
        assert call_kwargs.kwargs["normalize_embeddings"] is False


class TestGetDimension:
    """Tests for SemanticEncoder.get_dimension."""

    def test_get_dimension_loads_model_if_needed(self, mock_st_module, mock_torch):
        """Test that get_dimension loads model if not yet loaded."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        assert encoder._model is None

        dim = encoder.get_dimension()

        assert dim == 384
        assert encoder._model is not None

    def test_get_dimension_returns_cached_dimension(self, mock_st_module, mock_torch):
        """Test that get_dimension returns cached dimension after model load."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder._load_model()

        dim = encoder.get_dimension()

        assert dim == 384

    def test_get_dimension_fallback_default(self, mock_st_module, mock_torch):
        """Test that get_dimension falls back to 384 if dimension is None."""
        mock_st_module.SentenceTransformer.return_value.get_sentence_embedding_dimension.return_value = None
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder._load_model()

        dim = encoder.get_dimension()

        assert dim == 384


class TestGetModelInfo:
    """Tests for SemanticEncoder.get_model_info."""

    def test_get_model_info_before_model_load(self, mock_st_module, mock_torch):
        """Test get_model_info loads model via get_dimension call."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder(model_name="test-model")
        info = encoder.get_model_info()

        assert info["model_name"] == "test-model"
        assert info["dimension"] == 384
        assert "device" in info
        # get_dimension() triggers model loading, so _model is not None
        assert "max_seq_length" in info

    def test_get_model_info_after_model_load(self, mock_st_module, mock_torch):
        """Test get_model_info after model is loaded via model property."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        _ = encoder.model  # Use property to set self._model

        info = encoder.get_model_info()

        assert info["model_name"] == "paraphrase-multilingual-MiniLM-L12-v2"
        assert info["dimension"] == 384
        assert "device" in info
        assert "max_seq_length" in info


class TestWarmup:
    """Tests for SemanticEncoder.warmup."""

    def test_warmup_loads_model(self, mock_st_module, mock_torch):
        """Test that warmup loads the model."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [0.1] * 384, dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        assert encoder._model is None

        encoder.warmup()

        assert encoder._model is not None

    def test_warmup_performs_dummy_encoding(self, mock_st_module, mock_torch):
        """Test that warmup performs a dummy encoding."""
        mock_st_module.SentenceTransformer.return_value.encode.return_value = np.array(
            [0.1] * 384, dtype=np.float32
        )
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder.warmup()

        assert mock_st_module.SentenceTransformer.return_value.encode.call_count >= 1


class TestClearCache:
    """Tests for SemanticEncoder.clear_cache."""

    def test_clear_cache_removes_all_cached_models(self, mock_st_module, mock_torch):
        """Test that clear_cache removes all cached models."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder._load_model()
        assert len(SemanticEncoder._model_cache) > 0

        encoder.clear_cache()

        assert len(SemanticEncoder._model_cache) == 0

    def test_clear_cache_affects_all_instances(self, mock_st_module, mock_torch):
        """Test that clear_cache affects all encoder instances."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder1 = SemanticEncoder()
        encoder2 = SemanticEncoder()
        encoder1._load_model()

        encoder2.clear_cache()

        assert len(SemanticEncoder._model_cache) == 0


class TestGetCachedModels:
    """Tests for SemanticEncoder.get_cached_models."""

    def test_get_cached_models_empty(self, mock_st_module):
        """Test get_cached_models when cache is empty."""
        from vibesop.semantic.encoder import SemanticEncoder

        cached = SemanticEncoder.get_cached_models()
        assert cached == []

    def test_get_cached_models_returns_model_names(self, mock_st_module, mock_torch):
        """Test get_cached_models returns list of model names."""
        from vibesop.semantic.encoder import SemanticEncoder

        encoder = SemanticEncoder()
        encoder._load_model()

        cached = SemanticEncoder.get_cached_models()

        assert len(cached) == 1
        assert "paraphrase-multilingual-MiniLM-L12-v2" in cached

    def test_get_cached_models_multiple_models(self, mock_st_module, mock_torch):
        """Test get_cached_models with multiple models cached."""
        from vibesop.semantic.encoder import SemanticEncoder

        mock_st_module.SentenceTransformer.reset_mock()
        encoder1 = SemanticEncoder(model_name="model-a")
        encoder2 = SemanticEncoder(model_name="model-b")
        encoder1._load_model()
        encoder2._load_model()

        cached = SemanticEncoder.get_cached_models()

        assert len(cached) == 2
        assert "model-a" in cached
        assert "model-b" in cached
