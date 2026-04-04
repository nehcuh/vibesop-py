"""VibeSOP Semantic Recognition Module.

This module provides semantic matching capabilities for VibeSOP, using
Sentence Transformers to understand the meaning behind user queries
rather than just matching keywords.

Features:
    - True semantic understanding (not just TF-IDF)
    - Synonym recognition (e.g., "扫描" = "检查" = "scan")
    - Multilingual support (Chinese + English)
    - Multiple matching strategies
    - Performance optimized (< 20ms per query)

Example:
    >>> from vibesop.semantic import SemanticEncoder, VectorCache
    >>>
    >>> # Create encoder
    >>> encoder = SemanticEncoder()
    >>>
    >>> # Create cache
    >>> cache = VectorCache(cache_dir=Path(".vibe/cache/semantic"), encoder=encoder)
    >>>
    >>> # Encode query
    >>> vector = encoder.encode_query("scan for vulnerabilities")
    >>>
    >>> # Get pattern vector
    >>> pattern_vector = cache.get_or_compute("security/scan", ["scan for vulnerabilities"])
    >>>
    >>> # Calculate similarity
    >>> from vibesop.semantic import SimilarityCalculator
    >>> calc = SimilarityCalculator()
    >>> similarity = calc.calculate_single(vector, pattern_vector)
    >>> print(f"Similarity: {similarity:.2%}")
    Similarity: 87.45%
"""

from __future__ import annotations

import logging
from pathlib import Path

# Check if sentence-transformers is available
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# Conditional imports - only import if dependencies are available
if SENTENCE_TRANSFORMERS_AVAILABLE:
    from vibesop.semantic.encoder import SemanticEncoder
    from vibesop.semantic.similarity import SimilarityCalculator, SimilarityMetric
    from vibesop.semantic.cache import VectorCache
    from vibesop.semantic.strategies import (
        CosineSimilarityStrategy,
        HybridMatchingStrategy,
    )
else:
    # Create stub classes for type hints when not available
    SemanticEncoder = None  # type: ignore
    SimilarityCalculator = None  # type: ignore
    SimilarityMetric = None  # type: ignore
    VectorCache = None  # type: ignore
    CosineSimilarityStrategy = None  # type: ignore
    HybridMatchingStrategy = None  # type: ignore

# Models don't require sentence-transformers, so they're always imported
from vibesop.semantic.models import (
    EncoderConfig,
    SemanticConfig,
    SemanticMatch,
    SemanticMethod,
    SemanticPattern,
)

__all__ = [
    # Availability check
    "SENTENCE_TRANSFORMERS_AVAILABLE",
    "check_semantic_available",
    "require_semantic",
    # Core classes
    "SemanticEncoder",
    "SimilarityCalculator",
    "SimilarityMetric",
    # Data models
    "EncoderConfig",
    "SemanticConfig",
    "SemanticMatch",
    "SemanticMethod",
    "SemanticPattern",
    # Strategies
    "CosineSimilarityStrategy",
    "HybridMatchingStrategy",
    # Cache
    "VectorCache",
]

logger = logging.getLogger(__name__)


def check_semantic_available() -> bool:
    """Check if semantic matching features are available.

    Returns:
        True if sentence-transformers is installed, False otherwise.

    Example:
        >>> if check_semantic_available():
        ...     print("Semantic matching is available!")
        ... else:
        ...     print("Install with: pip install vibesop[semantic]")
    """
    return SENTENCE_TRANSFORMERS_AVAILABLE


def require_semantic() -> None:
    """Require semantic matching features, raising an error if unavailable.

    Raises:
        ImportError: If sentence-transformers is not installed.

    Example:
        >>> try:
        ...     require_semantic()
        ...     encoder = SemanticEncoder()
        ... except ImportError as e:
        ...     print(f"Error: {e}")
    """
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        raise ImportError(
            "Semantic matching requires sentence-transformers. "
            "Install with: pip install vibesop[semantic]"
        )


def get_semantic_info() -> dict[str, str | bool]:
    """Get information about semantic matching availability and configuration.

    Returns:
        Dictionary with keys:
        - available: Whether semantic matching is available
        - version: sentence-transformers version (if available)
        - model_default: Default model name
        - cache_dir_default: Default cache directory

    Example:
        >>> info = get_semantic_info()
        >>> info["available"]
        True
        >>> info["model_default"]
        'paraphrase-multilingual-MiniLM-L12-v2'
    """
    info = {
        "available": SENTENCE_TRANSFORMERS_AVAILABLE,
        "model_default": "paraphrase-multilingual-MiniLM-L12-v2",
        "cache_dir_default": ".vibe/cache/semantic",
    }

    if SENTENCE_TRANSFORMERS_AVAILABLE:
        try:
            import sentence_transformers

            info["version"] = sentence_transformers.__version__
        except Exception:
            info["version"] = "unknown"

    return info


def create_encoder(
    model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
    device: str = "auto",
    cache_dir: Path | None = None,
) -> SemanticEncoder:
    """Create a semantic encoder (convenience function).

    This is a convenience function that creates a SemanticEncoder
    with common defaults.

    Args:
        model_name: Name of the sentence transformer model.
        device: Device to use for inference.
        cache_dir: Directory for caching models.

    Returns:
        Configured SemanticEncoder instance.

    Raises:
        ImportError: If sentence-transformers is not installed.

    Example:
        >>> encoder = create_encoder()
        >>> vector = encoder.encode_query("Hello world")
    """
    require_semantic()

    return SemanticEncoder(
        model_name=model_name,
        device=device,
        cache_dir=cache_dir,
    )


def create_similarity_calculator(
    metric: str = "cosine",
    normalize: bool = True,
) -> SimilarityCalculator:
    """Create a similarity calculator (convenience function).

    This is a convenience function that creates a SimilarityCalculator
    with common defaults.

    Args:
        metric: Similarity metric to use.
        normalize: Whether to normalize output to [0, 1].

    Returns:
        Configured SimilarityCalculator instance.

    Example:
        >>> calc = create_similarity_calculator()
        >>> similarity = calc.calculate_single(v1, v2)
    """
    return SimilarityCalculator(metric=metric, normalize=normalize)
