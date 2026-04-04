# VibeSOP 质量重构计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 VibeSOP 从"功能丰富但质量欠债"状态重构为"功能完整且质量过硬"的生产级项目。

**Architecture:** 分 4 个独立阶段执行，每个阶段可独立提交、独立验证。P0 修复类型错误和补齐语义测试 → P1 重构膨胀模块 → P2 修复架构问题 → P3 清理与规范化。

**Tech Stack:** Python 3.12+, Pydantic v2, Typer, Pyright, Ruff, pytest

---

## 文件责任映射

### 需要重构的核心文件

| 文件 | 当前行数 | 问题 | 目标 |
|------|---------|------|------|
| `src/vibesop/cli/main.py` | 491 | 30+ 命令手动注册 | 拆为子命令组，自动发现 |
| `src/vibesop/core/routing/engine.py` | 659 | 5 层路由全塞一个类 | 每层独立 Handler |
| `src/vibesop/triggers/detector.py` | 614 | 两阶段检测+语义精炼重复代码 | 提取公共语义精炼逻辑 |

### 需要新增的文件

| 文件 | 职责 |
|------|------|
| `src/vibesop/core/routing/handlers.py` | 5 层路由 Handler 基类 + 各层实现 |
| `src/vibesop/core/routing/layer_registry.py` | Handler 注册表，替代 engine.py 中的硬编码 |
| `src/vibesop/cli/subcommands/__init__.py` | 子命令自动发现入口 |
| `src/vibesop/triggers/semantic_refiner.py` | 语义精炼公共逻辑（从 detector.py 提取） |

### 需要补充测试的文件

| 文件 | 当前覆盖率 | 目标覆盖率 |
|------|-----------|-----------|
| `src/vibesop/semantic/cache.py` | 0% | 85% |
| `src/vibesop/semantic/encoder.py` | 0% | 85% |
| `src/vibesop/semantic/similarity.py` | 0% | 85% |
| `src/vibesop/semantic/strategies.py` | 0% | 85% |
| `src/vibesop/semantic/models.py` | 60% | 85% |

---

## Phase 1: 紧急修复 — 类型错误 + 语义模块测试

### Task 1: 修复全部 Pyright 类型错误

LSP 扫描发现了 **100+ 类型错误**，分布在多个文件中。本任务集中修复。

**Files:**
- Modify: `src/vibesop/core/routing/engine.py`
- Modify: `src/vibesop/cli/main.py`
- Modify: `src/vibesop/core/models.py`
- Modify: `src/vibesop/triggers/detector.py`
- Modify: `src/vibesop/cli/commands/auto.py`

- [ ] **Step 1: 修复 engine.py 类型错误**

主要问题：
1. `dict[str, any]` → `dict[str, Any]` (line 509)
2. `list` 缺少类型参数 (lines 515, 596, 609, 615, 659)
3. `_get_alternatives` 返回 `list[Unknown]` — 需要完整类型注解
4. `routing_path` 类型不匹配 — `list[int]` 应转为 `list[Literal[0, 1, 2, 3, 4]]`
5. `_preference_learner` 是 protected member 在类外访问

```python
# engine.py 顶部添加：
from typing import Any, Literal

# 修复 get_preference_stats (line 509):
def get_preference_stats(self) -> dict[str, Any]:

# 修复 get_top_skills 返回类型 (line 515):
def get_top_skills(
    self,
    limit: int = 5,
    min_selections: int = 2,
) -> list[Any]:

# 修复 _get_alternatives 返回类型 (line 576):
def _get_alternatives(self, primary: SkillRoute) -> list[SkillRoute]:

# 修复 routing_path 类型 (line 187):
routing_path=[Literal(layer_num)],  # 或直接 cast

# 修复 _no_match_result 中的 routing_path (line 441):
routing_path=[],  # 已经是空列表，类型推断正确
```

- [ ] **Step 2: 修复 main.py 类型错误**

主要问题：
1. `installer.verify()` 返回 `Dict[str, Unknown]` — 需要 VibeSOPInstaller 类型注解
2. `_check_hooks` 中大量 Unknown 类型
3. `record` 命令访问 `_preference_learner` protected member
4. `route_stats` 中 `stats['total_routes']` 类型歧义（`int | dict[str, int]`）

```python
# main.py 修复 _check_hooks:
def _check_hooks() -> tuple[bool, str]:
    """Check hook installation status."""
    try:
        from vibesop.installer import VibeSOPInstaller

        installer = VibeSOPInstaller()
        platforms = installer.list_platforms()

        results: list[str] = []
        for platform_info in platforms:
            platform_name: str = platform_info["name"]
            verify_result: dict[str, Any] = installer.verify(platform_name)

            if verify_result.get("installed"):
                hooks_status: dict[str, bool] = verify_result.get("hooks_installed", {})
                hook_count = sum(1 for status in hooks_status.values() if status)
                total_hooks = len(hooks_status)
                results.append(f"{platform_name}: {hook_count}/{total_hooks}")
            else:
                results.append(f"{platform_name}: not installed")

        if results:
            return any("installed" not in r for r in results), "; ".join(results)
        else:
            return False, "No platforms checked"
    except Exception as e:
        return False, f"Failed to check: {e}"

# 修复 route_stats 中的类型歧义:
@app.command("route-stats")
def route_stats() -> None:
    """Show routing statistics."""
    router = SkillRouter()
    stats = router.get_stats()

    total: int = stats["total_routes"]
    console.print(f"[bold]📊 Routing Statistics[/bold]\n")
    console.print(f"Total routes: {total}")

    if total > 0:
        layer_dist: dict[str, int] = stats["layer_distribution"]
        console.print("\n[bold]Layer Distribution:[/bold]")
        for layer, count in layer_dist.items():
            pct = count / total * 100
            console.print(f"  • {layer}: {count} ({pct:.0f}%)")
```

- [ ] **Step 3: 修复 core/models.py 类型错误**

```python
# models.py RoutingResult — alternatives 和 routing_path 需要显式类型:
class RoutingResult(BaseModel):
    primary: SkillRoute
    alternatives: list[SkillRoute] = Field(
        default_factory=list,
        description="Alternative skill matches",
    )
    routing_path: list[Literal[0, 1, 2, 3, 4]] = Field(
        default_factory=list,
        description="Layers consulted during routing",
    )
```

- [ ] **Step 4: 修复 detector.py 类型错误**

主要问题：
1. numpy import 条件导入导致类型未知
2. `EncoderConfig` 在 TYPE_CHECKING 分支中引用

```python
# detector.py 顶部修复:
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from vibesop.semantic.models import EncoderConfig
else:
    try:
        import numpy as np
    except ImportError:
        np = None  # type: ignore[misc]

# 修复 semantic_config 参数类型:
def __init__(
    self,
    patterns: list[TriggerPattern],
    confidence_threshold: float = 0.6,
    enable_semantic: bool = False,
    semantic_config: "EncoderConfig | None" = None,
) -> None:
```

- [ ] **Step 5: 修复 auto.py 类型错误**

```python
# auto.py 添加类型注解:
def _show_match_details(match: PatternMatch, verbose: bool) -> None:
def _show_dry_run(match: PatternMatch, input_data: dict[str, Any]) -> None:
def _show_execution_result(result: dict[str, Any], verbose: bool) -> None:
def _show_no_match_detected(query: str, min_confidence: float, verbose: bool) -> None:

# 修复 input_dict 类型:
input_dict: dict[str, Any] = {}
```

- [ ] **Step 6: 验证所有类型错误已修复**

Run: `uv run pyright src/vibesop 2>&1 | grep -c "ERROR"`
Expected: 0 errors (或接近 0，剩余为可选依赖相关的可忽略错误)

- [ ] **Step 7: Commit**

```bash
git add src/vibesop/core/routing/engine.py src/vibesop/cli/main.py src/vibesop/core/models.py src/vibesop/triggers/detector.py src/vibesop/cli/commands/auto.py
git commit -m "fix: resolve 100+ pyright type errors across codebase"
```

---

### Task 2: 为 `semantic/models.py` 补测试

**Files:**
- Create: `tests/semantic/test_models.py`
- Read: `src/vibesop/semantic/models.py`

- [ ] **Step 1: 读取 models.py 了解所有模型**

Read: `src/vibesop/semantic/models.py`

- [ ] **Step 2: 编写测试**

```python
"""Tests for semantic data models."""

import pytest
from vibesop.semantic.models import (
    EncoderConfig,
    SemanticPattern,
    SemanticMatch,
    SemanticMethod,
)


class TestEncoderConfig:
    """Test EncoderConfig model."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = EncoderConfig()
        assert config.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
        assert config.device == "auto"
        assert config.batch_size == 32
        assert config.half_precision is True

    def test_custom_values(self) -> None:
        """Test custom configuration."""
        config = EncoderConfig(
            model_name="distiluse-base-multilingual-cased-v2",
            device="cpu",
            batch_size=16,
        )
        assert config.model_name == "distiluse-base-multilingual-cased-v2"
        assert config.device == "cpu"
        assert config.batch_size == 16

    def test_from_env_with_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test from_env when no env vars are set."""
        for var in ["VIBE_SEMANTIC_MODEL", "VIBE_SEMANTIC_DEVICE",
                     "VIBE_SEMANTIC_CACHE_DIR", "VIBE_SEMANTIC_BATCH_SIZE",
                     "VIBE_SEMANTIC_HALF_PRECISION"]:
            monkeypatch.delenv(var, raising=False)

        config = EncoderConfig.from_env()
        assert config.model_name == "paraphrase-multilingual-MiniLM-L12-v2"

    def test_from_env_with_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test from_env reads environment variables."""
        monkeypatch.setenv("VIBE_SEMANTIC_MODEL", "test-model")
        monkeypatch.setenv("VIBE_SEMANTIC_DEVICE", "cuda")
        monkeypatch.setenv("VIBE_SEMANTIC_BATCH_SIZE", "64")

        config = EncoderConfig.from_env()
        assert config.model_name == "test-model"
        assert config.device == "cuda"
        assert config.batch_size == 64


class TestSemanticPattern:
    """Test SemanticPattern model."""

    def test_create_pattern(self) -> None:
        """Test creating a semantic pattern."""
        pattern = SemanticPattern(
            pattern_id="test/pattern",
            examples=["example one", "example two"],
        )
        assert pattern.pattern_id == "test/pattern"
        assert len(pattern.examples) == 2
        assert pattern.embedding_vector is None

    def test_pattern_with_vector(self) -> None:
        """Test pattern with pre-computed vector."""
        import numpy as np
        vector = np.array([0.1, 0.2, 0.3])
        pattern = SemanticPattern(
            pattern_id="test/pattern",
            examples=["example"],
            embedding_vector=vector,
        )
        assert pattern.embedding_vector is not None


class TestSemanticMatch:
    """Test SemanticMatch model."""

    def test_create_match(self) -> None:
        """Test creating a semantic match."""
        match = SemanticMatch(
            pattern_id="test/pattern",
            score=0.85,
            method=SemanticMethod.COSINE,
        )
        assert match.pattern_id == "test/pattern"
        assert match.score == 0.85
        assert match.method == SemanticMethod.COSINE

    def test_match_with_metadata(self) -> None:
        """Test match with additional metadata."""
        match = SemanticMatch(
            pattern_id="test/pattern",
            score=0.9,
            method=SemanticMethod.HYBRID,
            model_used="test-model",
            encoding_time=0.015,
        )
        assert match.model_used == "test-model"
        assert match.encoding_time == 0.015


class TestSemanticMethod:
    """Test SemanticMethod enum."""

    def test_enum_values(self) -> None:
        """Test enum values."""
        assert SemanticMethod.COSINE.value == "cosine"
        assert SemanticMethod.HYBRID.value == "hybrid"
```

- [ ] **Step 3: 运行测试验证通过**

Run: `uv run pytest tests/semantic/test_models.py -v --no-cov`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/semantic/test_models.py
git commit -m "test: add tests for semantic models"
```

---

### Task 3: 为 `semantic/encoder.py` 补测试

**Files:**
- Create: `tests/semantic/test_encoder_unit.py`
- Read: `src/vibesop/semantic/encoder.py`

- [ ] **Step 1: 读取 encoder.py 了解接口**

Read: `src/vibesop/semantic/encoder.py`

- [ ] **Step 2: 编写单元测试（mock 模型加载）**

```python
"""Unit tests for SemanticEncoder (mocked, no real model loading)."""

import pytest
from unittest.mock import MagicMock, patch
from vibesop.semantic.encoder import SemanticEncoder


class TestSemanticEncoderInit:
    """Test SemanticEncoder initialization."""

    @patch("vibesop.semantic.encoder.SentenceTransformer")
    def test_init_with_defaults(self, mock_st: MagicMock) -> None:
        """Test initialization with default parameters."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        encoder = SemanticEncoder()

        mock_st.assert_called_once_with(
            "paraphrase-multilingual-MiniLM-L12-v2",
            device="auto",
        )
        assert encoder.model_name == "paraphrase-multilingual-MiniLM-L12-v2"

    @patch("vibesop.semantic.encoder.SentenceTransformer")
    def test_init_with_custom_params(self, mock_st: MagicMock) -> None:
        """Test initialization with custom parameters."""
        mock_model = MagicMock()
        mock_st.return_value = mock_model

        encoder = SemanticEncoder(
            model_name="test-model",
            device="cpu",
            batch_size=16,
        )

        mock_st.assert_called_once_with("test-model", device="cpu")
        assert encoder.batch_size == 16

    @patch("vibesop.semantic.encoder.SentenceTransformer")
    def test_encode_single_text(self, mock_st: MagicMock) -> None:
        """Test encoding a single text."""
        import numpy as np
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
        mock_st.return_value = mock_model

        encoder = SemanticEncoder()
        result = encoder.encode("hello world")

        assert result.shape == (3,)
        mock_model.encode.assert_called_once()

    @patch("vibesop.semantic.encoder.SentenceTransformer")
    def test_encode_batch(self, mock_st: MagicMock) -> None:
        """Test encoding multiple texts."""
        import numpy as np
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4]])
        mock_st.return_value = mock_model

        encoder = SemanticEncoder()
        result = encoder.encode(["hello", "world"])

        assert result.shape == (2, 2)

    @patch("vibesop.semantic.encoder.SentenceTransformer")
    def test_encode_query_convenience(self, mock_st: MagicMock) -> None:
        """Test encode_query convenience method."""
        import numpy as np
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.5, 0.5])
        mock_st.return_value = mock_model

        encoder = SemanticEncoder()
        result = encoder.encode_query("test query")

        assert result.shape == (2,)
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/semantic/test_encoder_unit.py -v --no-cov`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/semantic/test_encoder_unit.py
git commit -m "test: add unit tests for semantic encoder"
```

---

### Task 4: 为 `semantic/similarity.py` 补测试

**Files:**
- Create: `tests/semantic/test_similarity.py`
- Read: `src/vibesop/semantic/similarity.py`

- [ ] **Step 1: 读取 similarity.py**

Read: `src/vibesop/semantic/similarity.py`

- [ ] **Step 2: 编写测试**

```python
"""Tests for SimilarityCalculator."""

import numpy as np
import pytest
from vibesop.semantic.similarity import SimilarityCalculator


class TestCosineSimilarity:
    """Test cosine similarity metric."""

    def test_identical_vectors(self) -> None:
        """Identical vectors should have similarity 1.0."""
        calc = SimilarityCalculator(metric="cosine")
        vec = np.array([[0.5, 0.5, 0.707]])
        result = calc.calculate(vec[0], vec)
        assert pytest.approx(result[0], abs=1e-6) == 1.0

    def test_orthogonal_vectors(self) -> None:
        """Orthogonal vectors should have similarity 0.0."""
        calc = SimilarityCalculator(metric="cosine")
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([[0.0, 1.0, 0.0]])
        result = calc.calculate(a, b)
        assert pytest.approx(result[0], abs=1e-6) == 0.0

    def test_opposite_vectors(self) -> None:
        """Opposite vectors should have similarity 0.0 after normalization."""
        calc = SimilarityCalculator(metric="cosine", normalize=True)
        a = np.array([1.0, 0.0])
        b = np.array([[-1.0, 0.0]])
        result = calc.calculate(a, b)
        assert result[0] >= 0.0  # Normalized to [0, 1]


class TestDotProduct:
    """Test dot product metric."""

    def test_dot_product(self) -> None:
        """Test dot product calculation."""
        calc = SimilarityCalculator(metric="dot_product", normalize=True)
        a = np.array([1.0, 2.0])
        b = np.array([[3.0, 4.0]])
        result = calc.calculate(a, b)
        expected = 1.0 + 8.0  # 11.0
        assert result[0] > 0


class TestEuclidean:
    """Test euclidean distance metric."""

    def test_identical_vectors(self) -> None:
        """Identical vectors should have distance 0, similarity 1."""
        calc = SimilarityCalculator(metric="euclidean", normalize=True)
        vec = np.array([[0.5, 0.5]])
        result = calc.calculate(vec[0], vec)
        assert pytest.approx(result[0], abs=1e-6) == 1.0


class TestBatchProcessing:
    """Test batch similarity calculation."""

    def test_multiple_vectors(self) -> None:
        """Test calculating similarity against multiple vectors."""
        calc = SimilarityCalculator(metric="cosine")
        query = np.array([1.0, 0.0, 0.0])
        candidates = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.707, 0.707, 0.0],
        ])
        result = calc.calculate(query, candidates)
        assert len(result) == 3
        assert pytest.approx(result[0], abs=1e-6) == 1.0
        assert pytest.approx(result[1], abs=1e-6) == 0.0
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/semantic/test_similarity.py -v --no-cov`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/semantic/test_similarity.py
git commit -m "test: add tests for similarity calculator"
```

---

### Task 5: 为 `semantic/cache.py` 补测试

**Files:**
- Create: `tests/semantic/test_cache.py`
- Read: `src/vibesop/semantic/cache.py`

- [ ] **Step 1: 读取 cache.py**

Read: `src/vibesop/semantic/cache.py`

- [ ] **Step 2: 编写测试**

```python
"""Tests for VectorCache."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from vibesop.semantic.cache import VectorCache


class TestVectorCacheInit:
    """Test VectorCache initialization."""

    def test_init_creates_cache_dir(self) -> None:
        """Test that initialization creates the cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            mock_encoder = MagicMock()
            cache = VectorCache(cache_dir=cache_dir, encoder=mock_encoder)

            assert cache_dir.exists()
            assert cache.cache_dir == cache_dir

    def test_init_with_ttl(self) -> None:
        """Test initialization with TTL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_encoder = MagicMock()
            cache = VectorCache(
                cache_dir=Path(tmpdir),
                encoder=mock_encoder,
                ttl=3600,
            )
            assert cache.ttl == 3600


class TestVectorCacheOperations:
    """Test cache operations."""

    @patch("vibesop.semantic.cache.VectorCache._save_vector")
    @patch("vibesop.semantic.cache.VectorCache._load_vector")
    def test_get_or_compute_cache_hit(
        self, mock_load: MagicMock, mock_save: MagicMock
    ) -> None:
        """Test get_or_compute returns cached vector on hit."""
        import numpy as np
        cached_vector = np.array([0.1, 0.2, 0.3])
        mock_load.return_value = cached_vector
        mock_encoder = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = VectorCache(cache_dir=Path(tmpdir), encoder=mock_encoder)
            result = cache.get_or_compute("test-pattern", ["example"])

            np.testing.assert_array_equal(result, cached_vector)
            mock_encoder.encode.assert_not_called()

    @patch("vibesop.semantic.cache.VectorCache._save_vector")
    @patch("vibesop.semantic.cache.VectorCache._load_vector")
    def test_get_or_compute_cache_miss(
        self, mock_load: MagicMock, mock_save: MagicMock
    ) -> None:
        """Test get_or_compute computes and caches on miss."""
        import numpy as np
        mock_load.return_value = None
        expected_vector = np.array([0.5, 0.5])
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = expected_vector

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = VectorCache(cache_dir=Path(tmpdir), encoder=mock_encoder)
            result = cache.get_or_compute("test-pattern", ["example"])

            mock_encoder.encode.assert_called_once()
            np.testing.assert_array_equal(result, expected_vector)


class TestVectorCachePersistence:
    """Test cache persistence."""

    def test_save_and_load_vector(self) -> None:
        """Test saving and loading vectors from disk."""
        import numpy as np
        mock_encoder = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = VectorCache(cache_dir=Path(tmpdir), encoder=mock_encoder)
            vector = np.array([0.1, 0.2, 0.3])

            cache._save_vector("test-pattern", vector)
            loaded = cache._load_vector("test-pattern")

            assert loaded is not None
            np.testing.assert_array_equal(loaded, vector)

    def test_expired_vector_returns_none(self) -> None:
        """Test that expired vectors return None."""
        import numpy as np
        import time
        mock_encoder = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = VectorCache(
                cache_dir=Path(tmpdir),
                encoder=mock_encoder,
                ttl=1,  # 1 second TTL
            )
            vector = np.array([0.1, 0.2])
            cache._save_vector("test-pattern", vector)

            time.sleep(1.1)
            loaded = cache._load_vector("test-pattern")

            assert loaded is None
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/semantic/test_cache.py -v --no-cov`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/semantic/test_cache.py
git commit -m "test: add tests for vector cache"
```

---

### Task 6: 为 `semantic/strategies.py` 补测试

**Files:**
- Create: `tests/semantic/test_strategies.py`
- Read: `src/vibesop/semantic/strategies.py`

- [ ] **Step 1: 读取 strategies.py**

Read: `src/vibesop/semantic/strategies.py`

- [ ] **Step 2: 编写测试**

```python
"""Tests for matching strategies."""

from unittest.mock import MagicMock
import numpy as np
import pytest
from vibesop.semantic.strategies import (
    CosineSimilarityStrategy,
    HybridMatchingStrategy,
)


class TestCosineSimilarityStrategy:
    """Test pure cosine similarity strategy."""

    def test_match_high_similarity(self) -> None:
        """Test matching with high similarity."""
        strategy = CosineSimilarityStrategy(threshold=0.7)
        query_vector = np.array([0.8, 0.6])
        pattern_vectors = np.array([[0.8, 0.6], [0.1, 0.1]])
        pattern_ids = ["pattern-a", "pattern-b"]

        results = strategy.match(query_vector, pattern_vectors, pattern_ids)

        assert len(results) >= 1
        assert results[0].pattern_id == "pattern-a"
        assert results[0].score > 0.9

    def test_match_below_threshold(self) -> None:
        """Test matching when all similarities are below threshold."""
        strategy = CosineSimilarityStrategy(threshold=0.9)
        query_vector = np.array([1.0, 0.0])
        pattern_vectors = np.array([[0.0, 1.0]])
        pattern_ids = ["pattern-a"]

        results = strategy.match(query_vector, pattern_vectors, pattern_ids)

        assert len(results) == 0


class TestHybridMatchingStrategy:
    """Test hybrid matching strategy."""

    def test_hybrid_score_fusion(self) -> None:
        """Test that hybrid strategy combines scores."""
        strategy = HybridMatchingStrategy(
            threshold=0.5,
            keyword_weight=0.3,
            semantic_weight=0.7,
        )
        query_vector = np.array([0.5, 0.5])
        pattern_vectors = np.array([[0.5, 0.5]])
        pattern_ids = ["pattern-a"]

        # Mock keyword scores
        strategy._get_keyword_scores = MagicMock(
            return_value=[0.8]
        )

        results = strategy.match(query_vector, pattern_vectors, pattern_ids)

        assert len(results) >= 1
        # Score should be fusion of keyword (0.8 * 0.3) + semantic (~1.0 * 0.7)
        assert results[0].score > 0.5
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/semantic/test_strategies.py -v --no-cov`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/semantic/test_strategies.py
git commit -m "test: add tests for matching strategies"
```

---

### Task 7: 运行 Phase 1 验证 — 覆盖率检查

- [ ] **Step 1: 运行语义模块覆盖率检查**

Run: `uv run pytest tests/semantic/ -v --cov=src/vibesop/semantic --cov-report=term-missing`
Expected: semantic/ 模块覆盖率 ≥ 75%

- [ ] **Step 2: 运行 pyright 类型检查**

Run: `uv run pyright src/vibesop`
Expected: No errors (特别是 `any` 类型错误已修复)

- [ ] **Step 3: 运行 ruff 检查**

Run: `uv run ruff check src/vibesop`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "phase1: semantic module tests + type fix complete"
```

---

## Phase 2: 重构膨胀模块

### Task 8: 提取语义精炼公共逻辑

**Files:**
- Create: `src/vibesop/triggers/semantic_refiner.py`
- Modify: `src/vibesop/triggers/detector.py`

- [ ] **Step 1: 创建 SemanticRefiner 类**

```python
"""Semantic refinement logic extracted from KeywordDetector.

This module handles Stage 2 semantic refinement using sentence embeddings,
shared between _semantic_refine and _semantic_refine_all.
"""

from typing import Optional

import numpy as np

from vibesop.triggers.models import PatternMatch


class SemanticRefiner:
    """Applies semantic refinement to candidate pattern matches.

    Score Fusion Strategy:
    - Traditional score > 0.8: Keep as-is (high confidence)
    - Semantic score > 0.8: Use semantic score (high semantic confidence)
    - Otherwise: Weighted average (40% traditional + 60% semantic)
    """

    def __init__(
        self,
        encoder,
        cache,
        calculator,
        patterns: list,
    ) -> None:
        """Initialize semantic refiner.

        Args:
            encoder: SemanticEncoder instance
            cache: VectorCache instance
            calculator: SimilarityCalculator instance
            patterns: List of TriggerPattern objects
        """
        self.encoder = encoder
        self.cache = cache
        self.calculator = calculator
        self.patterns = {p.pattern_id: p for p in patterns}

    def refine(
        self,
        query: str,
        candidates: list[PatternMatch],
    ) -> list[PatternMatch]:
        """Apply semantic refinement to candidates.

        Updates candidates in-place with semantic scores.

        Args:
            query: User query
            candidates: Candidate matches from fast filter

        Returns:
            Same candidates list with updated semantic scores
        """
        if not candidates:
            return candidates

        # Encode query
        import time
        start_time = time.time()
        query_vector = self.encoder.encode_query(query)
        encoding_time = time.time() - start_time

        # Get pattern vectors
        pattern_vectors = self._get_pattern_vectors(candidates)
        if not pattern_vectors:
            return candidates

        # Calculate similarities
        matches_with_vectors = [m for m, _ in pattern_vectors]
        vectors = np.array([v for _, v in pattern_vectors])
        similarities = self.calculator.calculate(query_vector, vectors)

        # Fuse scores
        for match, similarity in zip(matches_with_vectors, similarities):
            final_score = self._fuse_scores(match.confidence, float(similarity))
            match.confidence = min(final_score, 1.0)
            match.semantic_score = float(similarity)
            match.semantic_method = "cosine"
            match.model_used = self.encoder.model_name
            match.encoding_time = encoding_time

        return candidates

    def _get_pattern_vectors(
        self,
        candidates: list[PatternMatch],
    ) -> list[tuple[PatternMatch, np.ndarray]]:
        """Get cached or computed vectors for candidates."""
        result = []
        for match in candidates:
            pattern = self.patterns.get(match.pattern_id)
            if not pattern:
                continue

            examples = pattern.examples + pattern.semantic_examples
            if not examples:
                examples = pattern.keywords + pattern.regex_patterns

            if examples:
                vector = self.cache.get_or_compute(pattern.pattern_id, examples)
                result.append((match, vector))

        return result

    @staticmethod
    def _fuse_scores(traditional: float, semantic: float) -> float:
        """Fuse traditional and semantic scores.

        Args:
            traditional: Traditional matching score
            semantic: Semantic similarity score

        Returns:
            Fused score
        """
        if traditional > 0.8:
            return traditional
        if semantic > 0.8:
            return semantic
        return traditional * 0.4 + semantic * 0.6
```

- [ ] **Step 2: 修改 detector.py 使用 SemanticRefiner**

在 `detector.py` 中：

```python
# 在 import 区域添加：
from vibesop.triggers.semantic_refiner import SemanticRefiner

# 在 _init_semantic_components 方法末尾添加：
self._refiner = SemanticRefiner(
    encoder=self.semantic_encoder,
    cache=self.semantic_cache,
    calculator=self.semantic_calculator,
    patterns=self.patterns,
)

# 替换 _semantic_refine 方法体：
def _semantic_refine(
    self,
    query: str,
    candidates: list[PatternMatch],
    threshold: float,
) -> Optional[PatternMatch]:
    """Stage 2: Semantic refinement."""
    if not candidates or not self._refiner:
        return max(candidates, key=lambda m: m.confidence) if candidates else None

    self._refiner.refine(query, candidates)
    best_match = max(candidates, key=lambda m: m.confidence)

    if best_match.confidence >= threshold:
        return best_match
    return None

# 替换 _semantic_refine_all 方法体：
def _semantic_refine_all(
    self,
    query: str,
    candidates: list[PatternMatch],
) -> None:
    """Apply semantic refinement to all candidates."""
    if not candidates or not self._refiner:
        return
    self._refiner.refine(query, candidates)
    candidates.sort(key=lambda m: m.confidence, reverse=True)
```

- [ ] **Step 3: 运行现有测试确保无回归**

Run: `uv run pytest tests/triggers/ -v --no-cov`
Expected: All existing tests pass

- [ ] **Step 4: 为 SemanticRefiner 编写测试**

Create: `tests/triggers/test_semantic_refiner.py`

```python
"""Tests for SemanticRefiner."""

from unittest.mock import MagicMock
import numpy as np
import pytest
from vibesop.triggers.semantic_refiner import SemanticRefiner
from vibesop.triggers.models import PatternMatch


class TestSemanticRefiner:
    """Test SemanticRefiner."""

    def test_fuse_scores_high_traditional(self) -> None:
        """High traditional score should be kept as-is."""
        result = SemanticRefiner._fuse_scores(0.9, 0.5)
        assert result == 0.9

    def test_fuse_scores_high_semantic(self) -> None:
        """High semantic score should be used."""
        result = SemanticRefiner._fuse_scores(0.5, 0.9)
        assert result == 0.9

    def test_fuse_scores_medium_both(self) -> None:
        """Medium scores should use weighted average."""
        result = SemanticRefiner._fuse_scores(0.5, 0.6)
        expected = 0.5 * 0.4 + 0.6 * 0.6
        assert pytest.approx(result) == expected

    def test_refine_updates_candidates(self) -> None:
        """Test that refine updates candidates with semantic scores."""
        mock_encoder = MagicMock()
        mock_encoder.encode_query.return_value = np.array([0.5, 0.5])
        mock_encoder.model_name = "test-model"

        mock_cache = MagicMock()
        mock_cache.get_or_compute.return_value = np.array([0.5, 0.5])

        mock_calc = MagicMock()
        mock_calc.calculate.return_value = [0.85]

        mock_pattern = MagicMock()
        mock_pattern.pattern_id = "test/pattern"
        mock_pattern.examples = ["example"]
        mock_pattern.semantic_examples = []
        mock_pattern.keywords = []
        mock_pattern.regex_patterns = []

        refiner = SemanticRefiner(
            encoder=mock_encoder,
            cache=mock_cache,
            calculator=mock_calc,
            patterns=[mock_pattern],
        )

        candidates = [PatternMatch(
            pattern_id="test/pattern",
            confidence=0.5,
        )]

        refiner.refine("test query", candidates)

        assert candidates[0].semantic_score == 0.85
        assert candidates[0].model_used == "test-model"
        assert candidates[0].encoding_time is not None
```

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/triggers/semantic_refiner.py src/vibesop/triggers/detector.py tests/triggers/test_semantic_refiner.py
git commit -m "refactor: extract SemanticRefiner from KeywordDetector to eliminate duplication"
```

---

### Task 9: 重构 engine.py — 5 层路由拆为独立 Handler

**Files:**
- Create: `src/vibesop/core/routing/handlers.py`
- Modify: `src/vibesop/core/routing/engine.py`

- [ ] **Step 1: 创建 Handler 基类和 5 层实现**

```python
"""Routing layer handlers.

Each layer of the 5-layer routing system is implemented as a
separate handler class with a common interface.
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from typing import Any

from vibesop.core.models import SkillRoute


class RoutingHandler(ABC):
    """Base class for routing layer handlers."""

    @property
    @abstractmethod
    def layer_number(self) -> int:
        """Return the layer number (0-4)."""

    @property
    @abstractmethod
    def layer_name(self) -> str:
        """Return human-readable layer name."""

    @abstractmethod
    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],
    ) -> SkillRoute | None:
        """Try to match the input.

        Args:
            normalized_input: Normalized user input
            context: Routing context

        Returns:
            SkillRoute if matched, None otherwise
        """


class AITriageHandler(RoutingHandler):
    """Layer 0: AI-Powered Semantic Triage using LLM."""

    def __init__(self, llm_client: Any, cache: Any, config: Any) -> None:
        self.llm = llm_client
        self.cache = cache
        self.config = config

    @property
    def layer_number(self) -> int:
        return 0

    @property
    def layer_name(self) -> str:
        return "ai_triage"

    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],
    ) -> SkillRoute | None:
        if not self.llm:
            return None

        cache_key = self.cache.generate_key(normalized_input, context)
        cached = self.cache.get(cache_key)
        if cached:
            return SkillRoute(**cached)

        prompt = self._build_prompt(normalized_input, context)

        try:
            response = self.llm.call(prompt=prompt, max_tokens=300, temperature=0.3)
            skill_id = self._parse_response(response.content)
            if skill_id:
                skill = self.config.get_skill_by_id(skill_id)
                if skill:
                    result = SkillRoute(
                        skill_id=skill["id"],
                        confidence=0.95,
                        layer=0,
                        source="ai_triage",
                    )
                    self.cache.set(cache_key, result.model_dump())
                    return result
        except (TimeoutError, ConnectionError, ValueError, KeyError) as e:
            if os.getenv("VIBE_DEBUG"):
                import warnings
                warnings.warn(f"AI triage call failed: {e}")

        return None

    def _build_prompt(self, input_text: str, context: dict[str, str | int]) -> str:
        skills_list = self.config.get_all_skills()
        skills_summary = "\n".join(
            f"- {s['id']}: {s.get('intent', 'N/A')}" for s in skills_list[:20]
        )
        context_str = f"\nContext: {context}" if context else ""
        return (
            f"Analyze the user request and select the most appropriate skill.\n\n"
            f"User request: {input_text}{context_str}\n\n"
            f"Available skills (top 20):\n{skills_summary}\n\n"
            f'Return ONLY the skill ID. Do not include any other text.\n\nSkill ID:'
        )

    def _parse_response(self, response: str) -> str | None:
        if match := re.search(r"```(?:json)?\s*(\S+)```", response):
            return match.group(1)
        if match := re.search(r"^[\w/-]+", response.strip(), re.MULTILINE):
            return match.group(0)
        return None


class ExplicitHandler(RoutingHandler):
    """Layer 1: Explicit skill invocation (/review, 使用 review)."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @property
    def layer_number(self) -> int:
        return 1

    @property
    def layer_name(self) -> str:
        return "explicit"

    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],  # noqa: ARG002
    ) -> SkillRoute | None:
        # Direct: /review
        if match := re.match(r"^/(\w+)", normalized_input):
            skill_id = f"/{match.group(1)}"
            skill = self.config.get_skill_by_id(skill_id)
            if skill:
                return SkillRoute(skill_id=skill["id"], confidence=1.0, layer=1, source="explicit")

        # Chinese: 使用 review / 调用 review
        if match := re.match(r"(?:使用|调用)\s*(\w+)", normalized_input):
            skill_id = f"/{match.group(1)}"
            skill = self.config.get_skill_by_id(skill_id)
            if skill:
                return SkillRoute(skill_id=skill["id"], confidence=1.0, layer=1, source="explicit")

        return None


class ScenarioHandler(RoutingHandler):
    """Layer 2: Scenario pattern matching (debug, test, review, refactor)."""

    # Move hardcoded mappings here where they belong
    SCENARIO_RULES = [
        {
            "keywords": ["bug", "error", "错误", "调试", "debug", "fix", "修复"],
            "skill_id": "systematic-debugging",
        },
        {
            "keywords": ["review", "审查", "评审", "检查"],
            "skill_id": "gstack/review",
            "fallback_id": "/review",
        },
        {
            "keywords": ["test", "测试", "tdd"],
            "skill_id": "superpowers/tdd",
            "fallback_id": "/test",
        },
        {
            "keywords": ["refactor", "重构"],
            "skill_id": "superpowers/refactor",
        },
    ]

    def __init__(self, config: Any) -> None:
        self.config = config

    @property
    def layer_number(self) -> int:
        return 2

    @property
    def layer_name(self) -> str:
        return "scenario"

    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],  # noqa: ARG002
    ) -> SkillRoute | None:
        for rule in self.SCENARIO_RULES:
            if any(kw in normalized_input for kw in rule["keywords"]):
                skill = self.config.get_skill_by_id(rule["skill_id"])
                if not skill and "fallback_id" in rule:
                    skill = self.config.get_skill_by_id(rule["fallback_id"])
                if skill:
                    return SkillRoute(
                        skill_id=skill["id"],
                        confidence=0.85,
                        layer=2,
                        source="scenario",
                    )
        return None


class SemanticHandler(RoutingHandler):
    """Layer 3: TF-IDF semantic matching."""

    def __init__(self, matcher: Any) -> None:
        self.matcher = matcher

    @property
    def layer_number(self) -> int:
        return 3

    @property
    def layer_name(self) -> str:
        return "semantic"

    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],  # noqa: ARG002
    ) -> SkillRoute | None:
        matches = self.matcher.match(normalized_input, top_k=1)
        if matches and matches[0].score >= 0.5:
            match = matches[0]
            return SkillRoute(
                skill_id=match.skill_id,
                confidence=match.score,
                layer=3,
                source="semantic",
            )
        return None


class FuzzyHandler(RoutingHandler):
    """Layer 4: Levenshtein fuzzy matching."""

    def __init__(self, matcher: Any) -> None:
        self.matcher = matcher

    @property
    def layer_number(self) -> int:
        return 4

    @property
    def layer_name(self) -> str:
        return "fuzzy"

    def try_match(
        self,
        normalized_input: str,
        context: dict[str, str | int],  # noqa: ARG002
    ) -> SkillRoute | None:
        matches = self.matcher.match(normalized_input, top_k=1)
        if matches and matches[0].score >= 0.7:
            match = matches[0]
            return SkillRoute(
                skill_id=match.skill_id,
                confidence=match.score,
                layer=4,
                source="fuzzy",
            )
        return None
```

- [ ] **Step 2: 重构 engine.py 使用 Handler 注册表**

```python
# engine.py 核心路由方法简化为：
def __init__(self, ...) -> None:
    # ... existing init ...
    self._handlers: list[RoutingHandler] = [
        AITriageHandler(self._llm, self._cache, self._config),
        ExplicitHandler(self._config),
        ScenarioHandler(self._config),
        SemanticHandler(self._semantic_matcher),
        FuzzyHandler(self._fuzzy_matcher),
    ]

def route(self, request: RoutingRequest) -> RoutingResult:
    self._stats.total_routes += 1
    normalized_input = self._normalize_input(request.query)

    for handler in self._handlers:
        result = handler.try_match(normalized_input, request.context)
        if result:
            layer_name = f"layer_{handler.layer_number}_{handler.layer_name}"
            self._stats.layer_distribution[layer_name] += 1
            boosted = self._apply_preference_boost(result, normalized_input)
            return RoutingResult(
                primary=boosted,
                alternatives=self._get_alternatives(boosted),
                routing_path=[handler.layer_number],
            )

    self._stats.layer_distribution["no_match"] += 1
    return self._no_match_result(normalized_input)
```

- [ ] **Step 3: 为 handlers.py 编写测试**

Create: `tests/core/routing/test_handlers.py`

```python
"""Tests for routing handlers."""

from unittest.mock import MagicMock
import pytest
from vibesop.core.routing.handlers import (
    ExplicitHandler,
    ScenarioHandler,
    SemanticRefiner._fuse_scores,
)


class TestExplicitHandler:
    """Test Layer 1 explicit handler."""

    def test_direct_invocation(self) -> None:
        """Test /skill invocation."""
        config = MagicMock()
        config.get_skill_by_id.return_value = {"id": "/review"}
        handler = ExplicitHandler(config)

        result = handler.try_match("/review this code", {})

        assert result is not None
        assert result.skill_id == "/review"
        assert result.confidence == 1.0
        assert result.layer == 1

    def test_chinese_invocation(self) -> None:
        """Test 使用 skill invocation."""
        config = MagicMock()
        config.get_skill_by_id.return_value = {"id": "/review"}
        handler = ExplicitHandler(config)

        result = handler.try_match("使用 review", {})

        assert result is not None
        assert result.confidence == 1.0


class TestScenarioHandler:
    """Test Layer 2 scenario handler."""

    def test_debug_scenario(self) -> None:
        """Test debug scenario matching."""
        config = MagicMock()
        config.get_skill_by_id.return_value = {"id": "systematic-debugging"}
        handler = ScenarioHandler(config)

        result = handler.try_match("help me debug this error", {})

        assert result is not None
        assert result.skill_id == "systematic-debugging"
        assert result.confidence == 0.85

    def test_no_match(self) -> None:
        """Test no scenario match."""
        config = MagicMock()
        config.get_skill_by_id.return_value = None
        handler = ScenarioHandler(config)

        result = handler.try_match("hello world", {})

        assert result is None
```

- [ ] **Step 4: 运行现有路由测试确保无回归**

Run: `uv run pytest tests/test_router_layers.py tests/test_routing_integration.py -v --no-cov`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/core/routing/handlers.py src/vibesop/core/routing/engine.py tests/core/routing/test_handlers.py
git commit -m "refactor: split 5-layer routing engine into separate handler classes"
```

---

### Task 10: 重构 main.py — 30+ 命令拆为子命令组

**Files:**
- Create: `src/vibesop/cli/subcommands/__init__.py`
- Modify: `src/vibesop/cli/main.py`

- [ ] **Step 1: 创建子命令自动发现机制**

```python
"""CLI subcommand registration with automatic discovery."""

import typer
from importlib import import_module
from pathlib import Path


def register_subcommands(app: typer.Typer) -> None:
    """Register all CLI subcommands from the commands directory.

    Each file in commands/ that defines a function matching the
    module name (with _cmd suffix) is automatically registered.
    """
    commands_dir = Path(__file__).parent.parent / "commands"

    # Core commands defined inline in main.py
    # (route, doctor, version, record, route-stats, preferences,
    #  top-skills, skills, skill-info)

    # Subcommand groups (Typer sub-apps)
    workflow_app = typer.Typer(help="Workflow management")
    app.add_typer(workflow_app, name="workflow")

    # Import and register workflow subcommands
    from vibesop.cli.commands import workflow as wf_module
    workflow_app.command("run")(wf_module._do_run_wrapper)
    workflow_app.command("list")(wf_module._do_list)
    workflow_app.command("resume")(wf_module._do_resume_wrapper)
    workflow_app.command("validate")(wf_module._do_validate_wrapper)

    # Semantic config subcommand
    config_app = typer.Typer(help="Configuration management")
    app.add_typer(config_app, name="config")

    # Register individual commands
    from vibesop.cli.commands import (
        init as init_mod,
        build as build_mod,
        deploy as deploy_mod,
        auto as auto_mod,
        config as config_mod,
        install as install_mod,
        hooks as hooks_mod,
        scan as scan_mod,
        checkpoint as checkpoint_mod,
        memory_cmd as memory_mod,
        worktree as worktree_mod,
        analyze as analyze_mod,
    )

    app.command()(init_mod.init)
    app.command()(build_mod.build)
    app.command()(deploy_mod.deploy)
    app.command()(auto_mod.auto)
    app.command()(config_mod.config)
    app.command()(install_mod.install)
    app.command()(hooks_mod.hooks)
    app.command()(scan_mod.scan)
    app.command()(checkpoint_mod.checkpoint)
    app.command("memory")(memory_mod.memory)
    app.command()(worktree_mod.worktree)
    app.command()(analyze_mod.analyze)
```

- [ ] **Step 2: 简化 main.py**

将 main.py 从 491 行缩减到 ~150 行：

```python
"""VibeSOP CLI - Main entry point."""

import importlib.util
import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from vibesop import __version__
from vibesop.core.models import RoutingRequest
from vibesop.core.routing.engine import SkillRouter
from vibesop.core.skills import SkillManager
from vibesop.cli.subcommands import register_subcommands

app = typer.Typer(
    name="vibe",
    help="VibeSOP - AI-powered workflow SOP",
    no_args_is_help=True,
)
console = Console()


@app.command()
def route(query: str = typer.Argument(...), json_output: bool = typer.Option(False, "--json", "-j")) -> None:
    """Route a query to the appropriate skill."""
    router = SkillRouter()
    request = RoutingRequest(query=query)
    result = router.route(request)

    if json_output:
        console.print_json(result.model_dump_json(indent=2))
    else:
        console.print(Panel(
            f"[bold green]✅ Matched:[/bold green] {result.primary.skill_id}\n"
            f"[dim]Confidence:[/dim] {result.primary.confidence:.0%}\n"
            f"[dim]Layer:[/dim] {result.primary.layer}\n"
            f"[dim]Source:[/dim] {result.primary.source}",
            title="[bold]Routing Result[/bold]",
            border_style="blue",
        ))
        if result.alternatives:
            console.print("\n[bold]💡 Alternatives:[/bold]")
            for alt in result.alternatives[:3]:
                console.print(f"  • {alt.skill_id} ({alt.confidence:.0%})")


@app.command()
def doctor() -> None:
    """Check environment and configuration."""
    # ... (keep existing doctor implementation)
    pass


@app.command()
def version() -> None:
    """Show version information."""
    console.print(Panel(
        f"[bold]VibeSOP[/bold] Python Edition\n\n"
        f"Version: {__version__}\nPython: 3.12+\nPydantic: v2",
        title="[bold]Version Information[/bold]",
        border_style="blue",
    ))


@app.command()
def record(skill_id: str = typer.Argument(...), query: str = typer.Argument(...),
           helpful: bool = typer.Option(True, "--helpful/--not-helpful", "-h/-H")) -> None:
    """Record a skill selection for preference learning."""
    router = SkillRouter()
    router.record_selection(skill_id, query, was_helpful=helpful)
    console.print(f"[green]✓[/green] Recorded selection: [bold]{skill_id}[/bold]")


# Stats commands
@app.command("route-stats")
def route_stats() -> None:
    """Show routing statistics."""
    router = SkillRouter()
    stats = router.get_stats()
    console.print(f"[bold]📊 Routing Statistics[/bold]\n")
    console.print(f"Total routes: {stats['total_routes']}")


@app.command("preferences")
def preferences() -> None:
    """Show preference learning statistics."""
    router = SkillRouter()
    stats = router.get_preference_stats()
    console.print(f"[bold]📊 Preference Learning[/bold]\n")
    console.print(f"Total selections: {stats['total_selections']}")


@app.command("top-skills")
def top_skills(limit: int = typer.Option(5, "--limit", "-l", min=1, max=10)) -> None:
    """Show most preferred skills."""
    router = SkillRouter()
    top = router.get_top_skills(limit=limit, min_selections=1)
    console.print(f"[bold]🏆 Top {len(top)} Preferred Skills[/bold]\n")
    for i, pref in enumerate(top, 1):
        console.print(f"{i}. [bold cyan]{pref.skill_id}[/bold cyan] - Score: {pref.score:.1%}")


@app.command("skills")
def skills_list(namespace: str | None = typer.Option(None, "--namespace", "-n"),
                verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """List all available skills."""
    manager = SkillManager()
    all_skills = manager.list_skills(namespace=namespace)
    if not all_skills:
        console.print("[yellow]No skills found.[/yellow]")
        return
    console.print(f"[bold]📚 Available Skills[/bold] ({len(all_skills)} total)\n")
    for skill in all_skills:
        console.print(f"  • [bold]{skill.get('id', 'unknown')}[/bold] - {skill.get('description', '')}")


@app.command("skill-info")
def skill_info(skill_id: str = typer.Argument(...)) -> None:
    """Show detailed information about a skill."""
    manager = SkillManager()
    info = manager.get_skill_info(skill_id)
    if not info:
        console.print(f"[red]Skill not found: {skill_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[bold]{info.get('name', info['id'])}[/bold]\n{info.get('description', 'No description')}")


# Register all subcommands
register_subcommands(app)


if __name__ == "__main__":
    app()
```

- [ ] **Step 3: 运行 CLI 测试确保无回归**

Run: `uv run pytest tests/test_cli.py tests/cli/ -v --no-cov`
Expected: All tests pass

- [ ] **Step 4: 验证 CLI 命令仍然可用**

Run: `uv run vibe --help`
Expected: Shows all commands including subcommand groups

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/cli/main.py src/vibesop/cli/subcommands/__init__.py
git commit -m "refactor: reorganize CLI into subcommand groups, reduce main.py from 491 to ~150 lines"
```

---

## Phase 3: 修复架构问题

### Task 11: 消除 engine.py 中的硬编码 skill ID

**Files:**
- Modify: `src/vibesop/core/routing/handlers.py` (ScenarioHandler)
- Create: `src/vibesop/core/routing/scenario_config.py`

- [ ] **Step 1: 创建场景配置文件**

```python
"""Scenario routing configuration.

Scenario patterns are configurable rather than hardcoded,
allowing users to customize which skills handle which scenarios.
"""

from __future__ import annotations

from typing import Any

DEFAULT_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "debug",
        "keywords": ["bug", "error", "错误", "调试", "debug", "fix", "修复"],
        "skill_id": "systematic-debugging",
        "confidence": 0.85,
    },
    {
        "name": "review",
        "keywords": ["review", "审查", "评审", "检查"],
        "skill_id": "gstack/review",
        "fallback_id": "/review",
        "confidence": 0.85,
    },
    {
        "name": "test",
        "keywords": ["test", "测试", "tdd"],
        "skill_id": "superpowers/tdd",
        "fallback_id": "/test",
        "confidence": 0.85,
    },
    {
        "name": "refactor",
        "keywords": ["refactor", "重构"],
        "skill_id": "superpowers/refactor",
        "confidence": 0.85,
    },
]
```

- [ ] **Step 2: 修改 ScenarioHandler 使用配置**

```python
class ScenarioHandler(RoutingHandler):
    """Layer 2: Scenario pattern matching."""

    def __init__(self, config: Any, scenarios: list[dict] | None = None) -> None:
        self.config = config
        self.scenarios = scenarios or DEFAULT_SCENARIOS

    def try_match(self, normalized_input: str, context: dict[str, str | int]) -> SkillRoute | None:
        for rule in self.scenarios:
            if any(kw in normalized_input for kw in rule["keywords"]):
                skill = self.config.get_skill_by_id(rule["skill_id"])
                if not skill and "fallback_id" in rule:
                    skill = self.config.get_skill_by_id(rule["fallback_id"])
                if skill:
                    return SkillRoute(
                        skill_id=skill["id"],
                        confidence=rule.get("confidence", 0.85),
                        layer=2,
                        source="scenario",
                    )
        return None
```

- [ ] **Step 3: Commit**

```bash
git add src/vibesop/core/routing/scenario_config.py src/vibesop/core/routing/handlers.py
git commit -m "refactor: make scenario rules configurable instead of hardcoded"
```

---

### Task 12: 统一版本号

**Files:**
- Modify: `pyproject.toml`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: 更新 pyproject.toml 版本号**

```toml
# Change line 3:
version = "2.2.0"
```

- [ ] **Step 2: 清理 CHANGELOG.md 中的 Future Releases**

删除已发布的 2.1.0 条目（它已经作为正式 release 存在）：

```markdown
# 删除这段：
### 2.1.0 (Planned)
- Machine learning-based pattern enhancement
- Pattern analytics and usage tracking
- Custom pattern builder CLI
- Multi-query support
- Confidence learning and adaptation
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "chore: sync version to 2.2.0, clean up stale future releases in changelog"
```

---

## Phase 4: CI/CD 与规范化

### Task 13: 增强 CI/CD

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: 添加覆盖率门槛到 CI**

```yaml
  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      # ... existing steps ...

      - name: Run tests with coverage
        run: uv run pytest --cov=src/vibesop --cov-report=xml --cov-report=term-missing --cov-fail-under=70
```

- [ ] **Step 2: 添加安全扫描 job**

```yaml
  security:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --extra dev

      - name: Run pip-audit
        run: uv run pip-audit
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add coverage gate (70%) and security scanning job"
```

---

### Task 14: 更新 CONTRIBUTING.md 中的过时引用

**Files:**
- Modify: `CONTRIBUTING.md`

- [ ] **Step 1: 检查并修复文档引用**

将底部的 Project-Specific 链接改为实际存在的文件：

```markdown
### Project-Specific
- [CLI Reference](docs/user/cli-reference.md)
- [Trigger Guide](docs/triggers/guide.md)
- [Semantic Guide](docs/semantic/guide.md)
- [Roadmap](docs/dev/roadmap-index.md)
```

- [ ] **Step 2: 添加架构说明文档**

Create: `docs/dev/architecture-overview.md`

```markdown
# Architecture Overview

## VibeSOP is a Tool, Not a Consumer

VibeSOP is a CLI tool that generates and manages workflow SOPs (Standard Operating
Procedures) for AI-assisted development. It is NOT a consumer of the skills it produces.

### Two Roles

**VibeSOP (this project)** — The "skill factory":
- Discovers skills from filesystem (gstack, superpowers, builtin)
- Routes natural language queries to the right skill (5-layer routing)
- Generates platform configuration (Claude Code, OpenCode)
- Installs hooks, integrations, and workflows

**Your project** — The "skill consumer":
- Run `vibe install claude-code` to generate `.claude/` config
- The generated config includes skills, rules, hooks
- Your AI assistant (Claude Code) then uses those skills

### Why This Repo Doesn't Have Skills Installed

This is the source code of the tool itself. Installing VibeSOP's own output into
its own source repo would be circular. Skills are meant for project repos where
AI assistants help you write code — not for the tool's own development.

### Skill Discovery vs Skill Installation

- `vibe skills` — Lists all skills VibeSOP can route to (discovery)
- `vibe install <platform>` — Generates config with those skills for a target project
- `vibe route "query"` — Routes a query to the best skill (uses 5-layer system)
- `vibe auto "query"` — Detects intent + auto-executes the matched skill
```

- [ ] **Step 3: Commit**

```bash
git add CONTRIBUTING.md docs/dev/architecture-overview.md
git commit -m "docs: fix stale references + add architecture overview explaining tool vs consumer roles"
```

---

## Phase 5: 最终验证

### Task 15: 全量验证

- [ ] **Step 1: 运行完整测试套件**

Run: `uv run pytest tests/ -v --cov=src/vibesop --cov-report=term-missing --cov-fail-under=70`
Expected: ≥ 70% coverage, all tests pass

- [ ] **Step 2: 运行类型检查**

Run: `uv run pyright src/vibesop`
Expected: 0 errors

- [ ] **Step 3: 运行 lint**

Run: `uv run ruff check src/vibesop`
Expected: 0 errors

- [ ] **Step 4: 格式化检查**

Run: `uv run ruff format --check src/vibesop`
Expected: All files formatted correctly

- [ ] **Step 5: 验证 CLI 可用性**

Run: `uv run vibe --help`
Run: `uv run vibe doctor`
Run: `uv run vibe route "test"`
Expected: All commands work

- [ ] **Step 6: 最终 Commit**

```bash
git add .
git commit -m "release: 2.2.0 quality release - tests, refactoring, CI/CD improvements"
```

---

## 验收标准

| 指标 | 当前 | 目标 | 验证方式 |
|------|------|------|---------|
| 总覆盖率 | 18.35% | ≥ 70% | `pytest --cov` |
| 语义模块覆盖率 | 0% | ≥ 80% | `pytest tests/semantic/ --cov` |
| main.py 行数 | 491 | ≤ 150 | `wc -l` |
| engine.py 行数 | 659 | ≤ 200 | `wc -l` |
| detector.py 行数 | 614 | ≤ 400 | `wc -l` |
| Pyright 错误 | 100+ | 0 | `pyright` |
| Ruff 错误 | 未知 | 0 | `ruff check` |
| CI 覆盖率门槛 | false | true (70%) | ci.yml |
| 类型注解缺失 | 多处 | 0 | LSP 扫描 |

## 执行顺序建议

1. **Phase 1** (Task 1-7): 立即执行 — 修复类型错误 + 补齐语义测试，这是最高优先级
2. **Phase 2** (Task 8-10): 紧随其后 — 重构膨胀模块，降低维护成本
3. **Phase 3** (Task 11-12): 架构改进 — 消除硬编码、统一版本号
4. **Phase 4** (Task 13-14): CI/CD 和文档 — 防止未来质量回退
5. **Phase 5** (Task 15): 最终验证 — 确保所有改动正常工作

每个 Phase 完成后都应该能通过 CI，可以独立发布。