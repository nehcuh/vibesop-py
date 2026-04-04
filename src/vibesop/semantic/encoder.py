"""Semantic vector encoder using Sentence Transformers.

This module provides a unified interface for encoding text into semantic vectors
using pre-trained sentence transformer models.

Key features:
- Lazy loading: Models are loaded on first use
- Device auto-detection: CUDA/MPS/CPU
- Batch encoding: Optimized for throughput
- Model caching: Global singleton to avoid duplicate loading
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class SemanticEncoder:
    """Semantic vector encoder using Sentence Transformers.

    This class provides a unified interface for encoding text into dense vector
    representations using pre-trained sentence transformer models. It supports
    multiple languages and is optimized for performance through lazy loading,
    batch processing, and model caching.

    Features:
        - Lazy loading: Model is loaded on first call to encode()
        - Device auto-detection: Automatically uses CUDA/MPS if available
        - Batch encoding: Process multiple texts efficiently
        - Half precision: FP16 inference for faster processing
        - Model caching: Global singleton prevents duplicate loading

    Example:
        >>> encoder = SemanticEncoder()
        >>> vector = encoder.encode("Hello world")
        >>> vector.shape
        (384,)
        >>> vectors = encoder.encode(["Hello", "World"], batch_size=32)
        >>> vectors.shape
        (2, 384)
    """

    # Class variable for model caching (global singleton)
    _model_cache: dict[str, Any] = {}

    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        device: str = "auto",
        cache_dir: Path | None = None,
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> None:
        """Initialize the semantic encoder.

        Args:
            model_name: Name of the sentence transformer model to use.
                Defaults to "paraphrase-multilingual-MiniLM-L12-v2".
                Other options:
                - "distiluse-base-multilingual-cased-v2" (256MB, balanced)
                - "paraphrase-multilingual-mpnet-base-v2" (568MB, best accuracy)
            device: Device to use for inference.
                - "auto": Automatically detect CUDA/MPS/CPU (default)
                - "cpu": Force CPU usage
                - "cuda": Force CUDA (GPU) usage
                - "mps": Force MPS (Apple Silicon GPU) usage
            cache_dir: Directory for caching models. If None, uses default.
            batch_size: Default batch size for encoding multiple texts.
            show_progress: Whether to show progress bar during encoding.

        Raises:
            ImportError: If sentence-transformers is not installed.
        """
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required for semantic encoding. "
                "Install with: pip install vibesop[semantic]"
            ) from e

        self.model_name = model_name
        self._device = device
        self._cache_dir = cache_dir
        self.batch_size = batch_size
        self.show_progress = show_progress

        # Model will be loaded lazily on first call to encode()
        self._model: SentenceTransformer | None = None

        # Vector dimension is determined by the model
        self._dimension: int | None = None

    def _load_model(self) -> SentenceTransformer:
        """Load the sentence transformer model (lazy loading).

        This method is called on first access to the model. It uses a class-level
        cache to avoid loading the same model multiple times.

        Returns:
            The loaded SentenceTransformer model.

        Note:
            Models are cached in a class variable, so multiple encoder instances
            with the same model_name will share the same model object.
        """
        # Check cache first
        if self.model_name in self._model_cache:
            logger.debug(f"Using cached model: {self.model_name}")
            return self._model_cache[self.model_name]

        logger.info(f"Loading model: {self.model_name}")
        import time

        start = time.time()

        # Import here to avoid unnecessary import overhead
        from sentence_transformers import SentenceTransformer

        # Build model kwargs
        model_kwargs = {}
        if self._cache_dir:
            model_kwargs["cache_folder"] = str(self._cache_dir)

        # Load model
        model = SentenceTransformer(
            self.model_name,
            device=self._get_device(),
            **model_kwargs,
        )

        elapsed = time.time() - start
        logger.info(f"Model loaded in {elapsed:.2f}s")

        # Cache the model
        self._model_cache[self.model_name] = model

        # Store dimension
        self._dimension = model.get_sentence_embedding_dimension()

        return model

    def _get_device(self) -> str:
        """Determine the device to use for inference.

        Returns:
            Device identifier for PyTorch ("cpu", "cuda", "mps").
        """
        if self._device != "auto":
            return self._device

        # Auto-detect device
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            elif torch.backends.mps.is_available():
                return "mps"
            else:
                return "cpu"
        except ImportError:
            return "cpu"

    @property
    def model(self) -> SentenceTransformer:
        """Get the model, loading it if necessary (lazy loading).

        Returns:
            The loaded SentenceTransformer model.
        """
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def encode(
        self,
        texts: str | list[str],
        batch_size: int | None = None,
        normalize: bool = True,
        show_progress: bool | None = None,
    ) -> np.ndarray:
        """Encode text(s) into semantic vectors.

        This method encodes single or multiple texts into dense vector representations.
        For multiple texts, batch processing is used for efficiency.

        Args:
            texts: Single text string or list of text strings to encode.
            batch_size: Number of texts to process in each batch.
                If None, uses the batch_size from __init__.
            normalize: Whether to L2-normalize vectors. Normalized vectors
                enable faster cosine similarity computation.
            show_progress: Whether to show progress bar for batch encoding.
                If None, uses the show_progress from __init__.

        Returns:
            Encoded vector(s) as numpy array.
            - Single text: shape (dim,)
            - Multiple texts: shape (n_texts, dim)

        Raises:
            ValueError: If texts is empty.
            ImportError: If sentence-transformers is not installed.

        Example:
            >>> encoder = SemanticEncoder()
            >>> vector = encoder.encode("Hello world")
            >>> vector.shape
            (384,)
            >>> vectors = encoder.encode(["Hello", "World"])
            >>> vectors.shape
            (2, 384)
        """
        if not texts:
            raise ValueError("texts cannot be empty")

        # Normalize input to list
        single_input = isinstance(texts, str)
        texts_list = [texts] if single_input else texts

        # Use default batch_size if not specified
        if batch_size is None:
            batch_size = self.batch_size

        # Use default show_progress if not specified
        if show_progress is None:
            show_progress = self.show_progress

        # Encode using the model
        embeddings = self.model.encode(
            texts_list,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=show_progress,
        )

        # Convert to numpy array if needed
        vectors = np.array(embeddings)

        # Return single vector if input was single text
        if single_input:
            return vectors[0]

        return vectors

    def encode_query(
        self,
        query: str,
        normalize: bool = True,
    ) -> np.ndarray:
        """Encode a single query text (optimized for single queries).

        This is a convenience method for encoding a single query, optimized
        for the common case of encoding user queries.

        Args:
            query: Query text to encode.
            normalize: Whether to L2-normalize the vector.

        Returns:
            Query vector as numpy array with shape (dim,).

        Example:
            >>> encoder = SemanticEncoder()
            >>> vector = encoder.encode_query("scan for vulnerabilities")
            >>> vector.shape
            (384,)
        """
        return self.encode(query, normalize=normalize)

    def get_dimension(self) -> int:
        """Get the dimension of the output vectors.

        Returns:
            Dimension of the output vectors (e.g., 384 for MiniLM-L12-v2).
        """
        if self._dimension is None:
            # Trigger model loading to get dimension
            _ = self.model

        return self._dimension if self._dimension else 384

    def get_model_info(self) -> dict[str, str | int]:
        """Get information about the loaded model.

        Returns:
            Dictionary with model information:
            - model_name: Name of the model
            - dimension: Output vector dimension
            - device: Device being used
            - max_seq_length: Maximum sequence length
        """
        info = {
            "model_name": self.model_name,
            "dimension": self.get_dimension(),
            "device": self._get_device(),
        }

        # Add max_seq_length if model is loaded
        if self._model is not None:
            info["max_seq_length"] = self._model.max_seq_length

        return info

    def warmup(self) -> None:
        """Warm up the encoder by loading the model.

        This method pre-loads the model and performs a dummy encoding to
        initialize all components. Useful for avoiding cold-start latency.

        Example:
            >>> encoder = SemanticEncoder()
            >>> encoder.warmup()  # Load model now, not on first encode()
            >>> # Later: encode() will be fast
        """
        logger.info("Warming up encoder...")
        _ = self.model  # Trigger model loading
        _ = self.encode("warmup")  # Perform dummy encoding
        logger.info("Encoder warmed up")

    def clear_cache(self) -> None:
        """Clear the model cache.

        This removes all cached models from memory. Useful for freeing
        resources when the encoder is no longer needed.

        Note:
            This affects all encoder instances that share the same model.

        Example:
            >>> encoder = SemanticEncoder()
            >>> encoder.clear_cache()
        """
        SemanticEncoder._model_cache.clear()
        logger.info("Model cache cleared")

    @classmethod
    def get_cached_models(cls) -> list[str]:
        """Get list of currently cached models.

        Returns:
            List of model names that are currently cached in memory.

        Example:
            >>> SemanticEncoder.get_cached_models()
            ['paraphrase-multilingual-MiniLM-L12-v2']
        """
        return list(cls._model_cache.keys())
