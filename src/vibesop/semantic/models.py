# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false, reportUnknownParameterType=false
"""Data models for semantic pattern matching.

This module defines the core data structures used in semantic matching,
including pattern representations, match results, and configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import numpy as np
else:
    try:
        import numpy as np
    except ImportError:
        np = None  # type: ignore


class SemanticMethod(str, Enum):
    """Methods for semantic matching."""

    COSINE = "cosine"
    HYBRID = "hybrid"


@dataclass
class SemanticPattern:
    """Semantic pattern with vector representation.

    This dataclass extends the basic pattern definition with semantic
    information, including pre-computed vectors and model details.

    Attributes:
        pattern_id: Unique identifier for the pattern.
        examples: Example queries that match this pattern.
        vector: Pre-computed semantic vector (optional).
        embedding_model: Name of the model used for embedding.
        threshold: Minimum similarity threshold for matching.

    Example:
        >>> pattern = SemanticPattern(
        ...     pattern_id="security/scan",
        ...     examples=["scan for vulnerabilities", "check for security issues"],
        ...     embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
        ... )
        >>> pattern.compute_vector(encoder)
    """

    pattern_id: str
    examples: list[str]
    vector: Any | None = None  # np.ndarray when available
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    threshold: float = 0.7

    def compute_vector(
        self,
        encoder: Any,
        strategy: str = "mean",
    ) -> Any:  # np.ndarray when available
        """Compute semantic vector for this pattern.

        Args:
            encoder: SemanticEncoder instance.
            strategy: Aggregation strategy for multiple examples.

        Returns:
            Pattern vector as numpy array.

        Raises:
            ValueError: If numpy is not available or no examples provided.
        """
        if np is None:
            raise ValueError(
                "numpy is required for vector computation. Install with: pip install vibesop[semantic]"
            )

        if not self.examples:
            raise ValueError(f"Cannot compute vector for pattern '{self.pattern_id}': no examples")

        # Encode all examples
        example_vectors = encoder.encode(self.examples, normalize=True)

        # Aggregate based on strategy
        if strategy == "mean":
            vector = np.mean(example_vectors, axis=0)
        elif strategy == "max":
            vector = example_vectors[0]
        else:
            raise ValueError(f"Unknown aggregation strategy: {strategy}")

        # Normalize to unit length
        vector = vector / (np.linalg.norm(vector) + 1e-8)

        # Store vector
        self.vector = vector

        return vector


@dataclass
class SemanticMatch:
    """Result of semantic pattern matching.

    This dataclass represents a match result from semantic matching,
    including both the pattern information and similarity scores.

    Attributes:
        pattern_id: ID of matched pattern.
        confidence: Overall confidence score (0.0 - 1.0).
        semantic_score: Semantic similarity score (0.0 - 1.0).
        semantic_method: Method used for semantic matching.
        vector_similarity: Raw vector similarity (optional).
        model_used: Name of embedding model used.
        encoding_time: Time to encode query (seconds).

    Example:
        >>> match = SemanticMatch(
        ...     pattern_id="security/scan",
        ...     confidence=0.92,
        ...     semantic_score=0.87,
        ...     semantic_method=SemanticMethod.COSINE,
        ... )
        >>> print(f"Matched: {match.pattern_id} with {match.confidence:.0%} confidence")
    """

    pattern_id: str
    confidence: float
    semantic_score: float
    semantic_method: SemanticMethod | str = SemanticMethod.COSINE
    vector_similarity: float | None = None
    model_used: str | None = None
    encoding_time: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert match to dictionary.

        Returns:
            Dictionary representation of the match.
        """
        return {
            "pattern_id": self.pattern_id,
            "confidence": self.confidence,
            "semantic_score": self.semantic_score,
            "semantic_method": str(self.semantic_method),
            "vector_similarity": self.vector_similarity,
            "model_used": self.model_used,
            "encoding_time": self.encoding_time,
        }


class EncoderConfig(BaseModel):
    """Configuration for semantic encoder.

    This model defines the configuration for the SemanticEncoder,
    including model selection, device settings, and performance options.

    Attributes:
        model_name: Name of the sentence transformer model.
        device: Device to use for inference.
        cache_dir: Directory for caching models.
        batch_size: Default batch size for encoding.
        show_progress: Whether to show progress bars.
        enable_half_precision: Whether to use FP16 inference.
        enable_model_cache: Whether to cache models in memory.

    Example:
        >>> config = EncoderConfig.from_env()
        >>> config.model_name
        'paraphrase-multilingual-MiniLM-L12-v2'
    """

    model_name: str = Field(
        default="paraphrase-multilingual-MiniLM-L12-v2",
        description="Name of the sentence transformer model",
    )

    device: Literal["auto", "cpu", "cuda", "mps"] = Field(
        default="auto",
        description="Device to use for inference",
    )

    cache_dir: Path | None = Field(
        default=None,
        description="Directory for caching models",
    )

    batch_size: int = Field(
        default=32,
        ge=1,
        le=256,
        description="Batch size for encoding multiple texts",
    )

    show_progress: bool = Field(
        default=False,
        description="Whether to show progress bars",
    )

    enable_half_precision: bool = Field(
        default=True,
        description="Whether to use FP16 inference (faster, less accurate)",
    )

    enable_model_cache: bool = Field(
        default=True,
        description="Whether to cache models in memory",
    )

    @classmethod
    def from_env(cls) -> "EncoderConfig":
        """Load configuration from environment variables.

        Returns:
            EncoderConfig instance with values from environment.

        Example:
            >>> import os
            >>> os.environ["VIBE_SEMANTIC_MODEL"] = "paraphrase-multilingual-mpnet-base-v2"
            >>> config = EncoderConfig.from_env()
            >>> config.model_name
            'paraphrase-multilingual-mpnet-base-v2'
        """
        import os

        return cls(
            model_name=os.getenv("VIBE_SEMANTIC_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"),
            device=os.getenv("VIBE_SEMANTIC_DEVICE", "auto"),  # type: ignore[reportArgumentType]
            cache_dir=Path(os.getenv("VIBE_SEMANTIC_CACHE_DIR", "")) or None,
            batch_size=int(os.getenv("VIBE_SEMANTIC_BATCH_SIZE", "32")),
            show_progress=os.getenv("VIBE_SEMANTIC_SHOW_PROGRESS", "").lower() == "true",
            enable_half_precision=os.getenv("VIBE_SEMANTIC_HALF_PRECISION", "true").lower()
            == "true",
            enable_model_cache=os.getenv("VIBE_SEMANTIC_MODEL_CACHE", "true").lower() == "true",
        )

    @classmethod
    def from_dict(cls, config: dict) -> "EncoderConfig":
        """Load configuration from dictionary.

        Args:
            config: Dictionary with configuration values.

        Returns:
            EncoderConfig instance.

        Example:
            >>> config = EncoderConfig.from_dict({
            ...     "model_name": "paraphrase-multilingual-mpnet-base-v2",
            ...     "device": "cuda",
            ... })
        """
        return cls(**config)

    def to_dict(self) -> dict:
        """Convert configuration to dictionary.

        Returns:
            Dictionary representation of the configuration.
        """
        return self.model_dump()


class SemanticConfig(BaseModel):
    """Complete semantic matching configuration.

    This model defines the full configuration for semantic matching,
    including encoder settings, matching strategy, and weights.

    Attributes:
        enabled: Whether semantic matching is enabled.
        encoder: Encoder configuration.
        strategy: Matching strategy to use.
        keyword_weight: Weight for keyword matching (in hybrid strategy).
        regex_weight: Weight for regex matching (in hybrid strategy).
        semantic_weight: Weight for semantic matching (in hybrid strategy).
        threshold: Minimum confidence threshold for semantic matches.

    Example:
        >>> config = SemanticConfig(enabled=True)
        >>> config.encoder.model_name
        'paraphrase-multilingual-MiniLM-L12-v2'
    """

    enabled: bool = Field(
        default=False,
        description="Whether semantic matching is enabled",
    )

    encoder: EncoderConfig = Field(
        default_factory=EncoderConfig,
        description="Encoder configuration",
    )

    strategy: Literal["cosine", "hybrid"] = Field(
        default="hybrid",
        description="Semantic matching strategy",
    )

    keyword_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Weight for keyword matching (hybrid strategy)",
    )

    regex_weight: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Weight for regex matching (hybrid strategy)",
    )

    semantic_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight for semantic matching (hybrid strategy)",
    )

    threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum semantic similarity threshold",
    )

    def validate_weights(self) -> None:
        """Validate that weights sum to 1.0 for hybrid strategy.

        Raises:
            ValueError: If weights don't sum to 1.0.
        """
        if self.strategy == "hybrid":
            total = self.keyword_weight + self.regex_weight + self.semantic_weight
            if abs(total - 1.0) > 0.01:
                raise ValueError(f"Weights must sum to 1.0 for hybrid strategy, got {total:.2f}")

    @classmethod
    def from_env(cls) -> "SemanticConfig":
        """Load configuration from environment variables.

        Returns:
            SemanticConfig instance with values from environment.

        Example:
            >>> import os
            >>> os.environ["VIBE_SEMANTIC_ENABLED"] = "true"
            >>> config = SemanticConfig.from_env()
            >>> config.enabled
            True
        """
        import os

        return cls(
            enabled=os.getenv("VIBE_SEMANTIC_ENABLED", "").lower() == "true",
            encoder=EncoderConfig.from_env(),
            strategy=os.getenv("VIBE_SEMANTIC_STRATEGY", "hybrid"),  # type: ignore[reportArgumentType]
            keyword_weight=float(os.getenv("VIBE_SEMANTIC_KEYWORD_WEIGHT", "0.3")),
            regex_weight=float(os.getenv("VIBE_SEMANTIC_REGEX_WEIGHT", "0.2")),
            semantic_weight=float(os.getenv("VIBE_SEMANTIC_SEMANTIC_WEIGHT", "0.5")),
            threshold=float(os.getenv("VIBE_SEMANTIC_THRESHOLD", "0.7")),
        )
