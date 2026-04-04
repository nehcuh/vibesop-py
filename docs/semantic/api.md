# Semantic Module API Reference

This document provides detailed API reference for the semantic recognition module.

## Module: `vibesop.semantic`

### Overview

```python
from vibesop.semantic import (
    # Availability checking
    SENTENCE_TRANSFORMERS_AVAILABLE,
    check_semantic_available,
    require_semantic,

    # Core classes
    SemanticEncoder,
    SimilarityCalculator,
    SimilarityMetric,

    # Data models
    EncoderConfig,
    SemanticConfig,
    SemanticMatch,
    SemanticMethod,
    SemanticPattern,

    # Strategies
    CosineSimilarityStrategy,
    HybridMatchingStrategy,

    # Cache
    VectorCache,
)
```

## Availability Checking

### `SENTENCE_TRANSFORMERS_AVAILABLE`

```python
SENTENCE_TRANSFORMERS_AVAILABLE: bool
```

Global flag indicating whether sentence-transformers is installed.

**Example**:
```python
from vibesop.semantic import SENTENCE_TRANSFORMERS_AVAILABLE

if SENTENCE_TRANSFORMERS_AVAILABLE:
    print("Semantic matching is available!")
else:
    print("Install with: pip install vibesop[semantic]")
```

### `check_semantic_available()`

```python
def check_semantic_available() -> bool
```

Check if semantic matching features are available.

**Returns**: `True` if sentence-transformers is installed, `False` otherwise.

**Example**:
```python
from vibesop.semantic import check_semantic_available

if check_semantic_available():
    encoder = SemanticEncoder()
```

### `require_semantic()`

```python
def require_semantic() -> None
```

Require semantic matching features, raising an error if unavailable.

**Raises**: `ImportError` if sentence-transformers is not installed.

**Example**:
```python
from vibesop.semantic import require_semantic, SemanticEncoder

try:
    require_semantic()
    encoder = SemanticEncoder()
except ImportError as e:
    print(f"Error: {e}")
```

## SemanticEncoder

### Class Definition

```python
class SemanticEncoder:
    """Semantic text encoder using Sentence Transformers."""

    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        device: str = "auto",
        cache_dir: Path | None = None,
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> None:
        """Initialize encoder.

        Args:
            model_name: Name of sentence transformer model.
            device: Device for inference (auto, cpu, cuda, mps).
            cache_dir: Directory for caching models.
            batch_size: Default batch size for encoding.
            show_progress: Whether to show progress bars.
        """

    def encode(
        self,
        texts: str | list[str],
        batch_size: int | None = None,
        normalize: bool = True,
    ) -> np.ndarray:
        """Encode text(s) into semantic vectors.

        Args:
            texts: Single text string or list of texts.
            batch_size: Batch size for encoding (uses default if None).
            normalize: Whether to L2 normalize vectors.

        Returns:
            Vector(s) as numpy array.
            - Single text: shape (384,)
            - List of texts: shape (n, 384)

        Raises:
            ValueError: If texts is empty or invalid.

        Example:
            >>> encoder = SemanticEncoder()
            >>> vector = encoder.encode("Hello world")
            >>> vector.shape
            (384,)
            >>> vectors = encoder.encode(["Hello", "World"])
            >>> vectors.shape
            (2, 384)
        """

    def encode_query(
        self,
        query: str,
        normalize: bool = True,
    ) -> np.ndarray:
        """Encode a query string (convenience method).

        Args:
            query: Query text.
            normalize: Whether to L2 normalize vector.

        Returns:
            Query vector as 1D numpy array.

        Example:
            >>> encoder = SemanticEncoder()
            >>> vector = encoder.encode_query("scan for vulnerabilities")
            >>> vector.shape
            (384,)
        """

    def warmup(self) -> None:
        """Warmup encoder by loading model and doing dummy encoding.

        Example:
            >>> encoder = SemanticEncoder()
            >>> encoder.warmup()  # Pre-load model
        """

    def get_dimension(self) -> int:
        """Get the dimension of output vectors.

        Returns:
            Vector dimension (e.g., 384 for MiniLM-L12-v2).

        Example:
            >>> encoder = SemanticEncoder()
            >>> encoder.get_dimension()
            384
        """

    def get_model_info(self) -> dict[str, Any]:
        """Get information about the loaded model.

        Returns:
            Dict with keys: model_name, dimension, device.

        Example:
            >>> encoder = SemanticEncoder()
            >>> info = encoder.get_model_info()
            >>> info["model_name"]
            'paraphrase-multilingual-MiniLM-L12-v2'
        """

    @classmethod
    def clear_cache(cls) -> None:
        """Clear model cache.

        Example:
            >>> SemanticEncoder.clear_cache()
        """

    @classmethod
    def get_cached_models(cls) -> list[str]:
        """Get list of cached model names.

        Returns:
            List of model names.

        Example:
            >>> SemanticEncoder.get_cached_models()
            ['paraphrase-multilingual-MiniLM-L12-v2']
        """
```

## SimilarityCalculator

### Class Definition

```python
class SimilarityCalculator:
    """Vector similarity calculator."""

    def __init__(
        self,
        metric: Literal["cosine", "dot", "euclidean", "manhattan"] = "cosine",
        normalize: bool = True,
    ) -> None:
        """Initialize calculator.

        Args:
            metric: Similarity metric to use.
            normalize: Whether to normalize output to [0, 1].

        Example:
            >>> calc = SimilarityCalculator(metric="cosine")
        """

    def calculate(
        self,
        query_vector: np.ndarray,
        pattern_vectors: np.ndarray,
    ) -> np.ndarray:
        """Calculate similarities between query and patterns.

        Args:
            query_vector: Query vector (1D, shape: [dim]).
            pattern_vectors: Pattern vectors (2D, shape: [n, dim]).

        Returns:
            Similarity scores (1D, shape: [n]) in range [0, 1].

        Raises:
            ValueError: If dimensions mismatch.

        Example:
            >>> calc = SimilarityCalculator()
            >>> query = np.random.rand(384)
            >>> patterns = np.random.rand(5, 384)
            >>> similarities = calc.calculate(query, patterns)
            >>> similarities.shape
            (5,)
        """

    def calculate_single(
        self,
        query_vector: np.ndarray,
        pattern_vector: np.ndarray,
    ) -> float:
        """Calculate similarity between two vectors.

        Args:
            query_vector: Query vector (1D).
            pattern_vector: Pattern vector (1D).

        Returns:
            Similarity score in range [0, 1].

        Example:
            >>> calc = SimilarityCalculator()
            >>> v1 = np.random.rand(384)
            >>> v2 = np.random.rand(384)
            >>> similarity = calc.calculate_single(v1, v2)
            >>> 0.0 <= similarity <= 1.0
            True
        """

    def batch_calculate(
        self,
        query_vectors: np.ndarray,
        pattern_vectors: np.ndarray,
    ) -> np.ndarray:
        """Calculate similarities for multiple queries.

        Args:
            query_vectors: Query vectors (2D, shape: [m, dim]).
            pattern_vectors: Pattern vectors (2D, shape: [n, dim]).

        Returns:
            Similarity matrix (2D, shape: [m, n]) in range [0, 1].

        Example:
            >>> calc = SimilarityCalculator()
            >>> queries = np.random.rand(10, 384)
            >>> patterns = np.random.rand(5, 384)
            >>> sim_matrix = calc.batch_calculate(queries, patterns)
            >>> sim_matrix.shape
            (10, 5)
        """

    def get_metric(self) -> str:
        """Get current metric name.

        Returns:
            Metric name string.

        Example:
            >>> calc = SimilarityCalculator(metric="cosine")
            >>> calc.get_metric()
            'cosine'
        """

    def set_metric(self, metric: str) -> None:
        """Change similarity metric.

        Args:
            metric: New metric name.

        Raises:
            ValueError: If metric is unknown.

        Example:
            >>> calc = SimilarityCalculator()
            >>> calc.set_metric("dot")
        """
```

## VectorCache

### Class Definition

```python
class VectorCache:
    """Cache for semantic pattern vectors."""

    def __init__(
        self,
        cache_dir: Path,
        encoder: SemanticEncoder,
        ttl: int = 86400,
    ) -> None:
        """Initialize cache.

        Args:
            cache_dir: Directory for cache storage.
            encoder: SemanticEncoder instance.
            ttl: Time-to-live for cache entries in seconds (default: 24h).

        Example:
            >>> from vibesop.semantic import SemanticEncoder, VectorCache
            >>> encoder = SemanticEncoder()
            >>> cache = VectorCache(
            ...     cache_dir=Path(".vibe/cache/semantic"),
            ...     encoder=encoder,
            ... )
        """

    def get_or_compute(
        self,
        pattern_id: str,
        examples: list[str],
    ) -> np.ndarray:
        """Get or compute pattern vector.

        Args:
            pattern_id: Pattern identifier.
            examples: Example texts for the pattern.

        Returns:
            Pattern vector as numpy array.

        Raises:
            ValueError: If examples is empty.

        Example:
            >>> vector = cache.get_or_compute(
            ...     "security/scan",
            ...     ["scan for vulnerabilities", "check security"],
            ... )
        """

    def preload_patterns(
        self,
        patterns: dict[str, list[str]],
    ) -> None:
        """Precompute vectors for multiple patterns.

        Args:
            patterns: Dict mapping pattern_id to examples.

        Example:
            >>> patterns = {
            ...     "security/scan": ["scan vulnerabilities"],
            ...     "dev/test": ["run tests"],
            ... }
            >>> cache.preload_patterns(patterns)
        """

    def save_to_disk(self) -> None:
        """Save cache to disk.

        Example:
            >>> cache.save_to_disk()
        """

    def invalidate_pattern(self, pattern_id: str) -> None:
        """Remove pattern from cache.

        Args:
            pattern_id: Pattern identifier.

        Example:
            >>> cache.invalidate_pattern("security/scan")
        """

    def invalidate_all(self) -> None:
        """Clear entire cache.

        Example:
            >>> cache.invalidate_all()
        """

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with keys: hits, misses, total_requests, hit_rate,
            size, size_bytes, size_mb.

        Example:
            >>> stats = cache.get_cache_stats()
            >>> stats["hit_rate"]
            0.95
        """
```

## Data Models

### EncoderConfig

```python
class EncoderConfig(BaseModel):
    """Configuration for SemanticEncoder."""

    model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    cache_dir: Path | None = None
    batch_size: int = 32
    show_progress: bool = False
    enable_half_precision: bool = True
    enable_model_cache: bool = True

    @classmethod
    def from_env(cls) -> "EncoderConfig:
        """Load configuration from environment variables.

        Example:
            >>> import os
            >>> os.environ["VIBE_SEMANTIC_MODEL"] = "distiluse-base-multilingual-cased-v2"
            >>> config = EncoderConfig.from_env()
            >>> config.model_name
            'distiluse-base-multilingual-cased-v2'
        """

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Example:
            >>> config = EncoderConfig()
            >>> d = config.to_dict()
        """
```

### SemanticPattern

```python
@dataclass
class SemanticPattern:
    """Semantic pattern with vector representation."""

    pattern_id: str
    examples: list[str]
    vector: np.ndarray | None = None
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    threshold: float = 0.7

    def compute_vector(
        self,
        encoder: SemanticEncoder,
        strategy: str = "mean",
    ) -> np.ndarray:
        """Compute semantic vector for this pattern.

        Args:
            encoder: SemanticEncoder instance.
            strategy: Aggregation strategy ("mean" or "max").

        Returns:
            Pattern vector as numpy array.

        Raises:
            ValueError: If no examples or unknown strategy.

        Example:
            >>> pattern = SemanticPattern(
            ...     pattern_id="test",
            ...     examples=["example 1", "example 2"],
            ... )
            >>> vector = pattern.compute_vector(encoder)
        """
```

### SemanticMatch

```python
@dataclass
class SemanticMatch:
    """Result of semantic pattern matching."""

    pattern_id: str
    confidence: float
    semantic_score: float
    semantic_method: SemanticMethod | str = SemanticMethod.COSINE
    vector_similarity: float | None = None
    model_used: str | None = None
    encoding_time: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert match to dictionary.

        Example:
            >>> match = SemanticMatch(
            ...     pattern_id="test",
            ...     confidence=0.9,
            ...     semantic_score=0.85,
            ... )
            >>> d = match.to_dict()
        """
```

### SemanticMethod

```python
class SemanticMethod(str, Enum):
    """Methods for semantic matching."""

    COSINE = "cosine"
    HYBRID = "hybrid"
```

## Matching Strategies

### CosineSimilarityStrategy

```python
class CosineSimilarityStrategy(MatchingStrategy):
    """Pure cosine similarity matching strategy."""

    def match(
        self,
        query: str,
        patterns: list[SemanticPattern],
    ) -> list[SemanticMatch]:
        """Match query against patterns using cosine similarity.

        Args:
            query: Query text.
            patterns: List of semantic patterns.

        Returns:
            List of matches sorted by confidence (descending).

        Example:
            >>> strategy = CosineSimilarityStrategy(encoder, cache)
            >>> matches = strategy.match("scan vulnerabilities", patterns)
        """
```

### HybridMatchingStrategy

```python
class HybridMatchingStrategy(MatchingStrategy):
    """Hybrid strategy combining traditional and semantic matching."""

    def __init__(
        self,
        encoder: SemanticEncoder,
        cache: VectorCache,
        keyword_weight: float = 0.3,
        regex_weight: float = 0.2,
        semantic_weight: float = 0.5,
        threshold: float = 0.7,
    ):
        """Initialize hybrid strategy.

        Args:
            encoder: SemanticEncoder instance.
            cache: VectorCache instance.
            keyword_weight: Weight for keyword matching (default: 0.3).
            regex_weight: Weight for regex matching (default: 0.2).
            semantic_weight: Weight for semantic matching (default: 0.5).
            threshold: Confidence threshold (default: 0.7).

        Raises:
            ValueError: If weights don't sum to 1.0.

        Example:
            >>> strategy = HybridMatchingStrategy(
            ...     encoder,
            ...     cache,
            ...     keyword_weight=0.4,
            ...     semantic_weight=0.6,
            ... )
        """

    def match(
        self,
        query: str,
        patterns: list[SemanticPattern],
    ) -> list[SemanticMatch]:
        """Match query using hybrid approach.

        Args:
            query: Query text.
            patterns: List of semantic patterns.

        Returns:
            List of matches sorted by confidence (descending).

        Example:
            >>> strategy = HybridMatchingStrategy(encoder, cache)
            >>> matches = strategy.match("scan vulnerabilities", patterns)
        """
```

## Integration with KeywordDetector

### Extended Parameters

```python
from vibesop.triggers import KeywordDetector
from vibesop.semantic.models import EncoderConfig

# Create semantic configuration
config = EncoderConfig(
    model_name="paraphrase-multilingual-MiniLM-L12-v2",
    device="auto",
)

# Initialize detector with semantic
detector = KeywordDetector(
    patterns=DEFAULT_PATTERNS,
    confidence_threshold=0.6,
    enable_semantic=True,
    semantic_config=config,
)

# Detect intent
match = detector.detect_best("帮我检查代码安全问题")

# Access semantic information
if match.semantic_score:
    print(f"Semantic score: {match.semantic_score:.0%}")
    print(f"Method: {match.semantic_method}")
    print(f"Model: {match.model_used}")
    print(f"Encoding time: {match.encoding_time*1000:.1f}ms")
```

### PatternMatch Extension

```python
class PatternMatch(BaseModel):
    """Extended with semantic fields."""

    # Traditional fields
    pattern_id: str
    confidence: float
    metadata: dict[str, Any]
    matched_keywords: list[str]
    matched_regex: list[str]
    semantic_score: float | None  # NEW

    # New semantic fields (v2.1.0)
    semantic_method: str | None  # NEW
    model_used: str | None  # NEW
    encoding_time: float | None  # NEW
```

## Error Handling

### ImportError

```python
from vibesop.semantic import require_semantic, SemanticEncoder

try:
    require_semantic()
    encoder = SemanticEncoder()
except ImportError as e:
    print(f"Sentence-transformers not installed: {e}")
    print("Install with: pip install vibesop[semantic]")
```

### ValueError

```python
from vibesop.semantic import SemanticEncoder, VectorCache

encoder = SemanticEncoder()
cache = VectorCache(Path(".cache"), encoder)

try:
    # Empty examples raises ValueError
    vector = cache.get_or_compute("pattern", [])
except ValueError as e:
    print(f"Invalid input: {e}")
```

## Performance Considerations

### Model Caching

Models are cached globally:

```python
# First load
encoder1 = SemanticEncoder()
encoder1.encode("test")  # Loads model (500ms)

# Second load - uses cached model
encoder2 = SemanticEncoder()
encoder2.encode("test")  # Instant (uses cache)

# Clear cache if needed
SemanticEncoder.clear_cache()
```

### Lazy Loading

Models load on first use:

```python
# Creating encoder is fast (no model loaded)
encoder = SemanticEncoder()

# First encode triggers model load
encoder.encode("test")  # Loads model here (500ms)

# Subsequent encodes are fast
encoder.encode("test2")  # Fast (8ms)
```

### Batch Processing

Batch processing is more efficient:

```python
# Slower: individual encoding
for text in texts:
    vector = encoder.encode(text)  # Multiple model calls

# Faster: batch encoding
vectors = encoder.encode(texts, batch_size=32)  # Single model call
```

## See Also

- [Semantic Matching Guide](./guide.md) - User guide for semantic features
- [Configuration Reference](./config.md) - Configuration options
- [Performance Guide](./performance.md) - Performance optimization
