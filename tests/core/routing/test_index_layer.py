"""Tests for the skill semantic index routing layer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.models import LayerDetail, RoutingLayer
from vibesop.core.routing import UnifiedRouter
from vibesop.core.routing._layers import (
    _compute_index_score,
    _tokenize_query,
    try_index_layer,
)
from vibesop.core.skills.indexer import SkillProfile


class TestTokenizeQuery:
    """Test query tokenization."""

    def test_english_words(self) -> None:
        tokens = _tokenize_query("review this code for security issues")
        assert "review" in tokens
        assert "code" in tokens
        assert "security" in tokens
        assert "issues" in tokens
        # Single char words excluded
        assert "a" not in tokens

    def test_cjk_characters(self) -> None:
        tokens = _tokenize_query("帮我审查代码")
        # CJK is tokenized as bigrams over contiguous runs
        assert "帮我" in tokens
        assert "我审" in tokens
        assert "审查" in tokens
        assert "查代" in tokens
        assert "代码" in tokens
        # Single chars are no longer tokens for multi-char runs
        assert "帮" not in tokens
        assert "审" not in tokens

    def test_single_cjk_char_keeps_unigram(self) -> None:
        tokens = _tokenize_query("好")
        assert tokens == {"好"}

    def test_cjk_run_separated_by_non_cjk(self) -> None:
        # Non-CJK characters break runs: no bigram may bridge across them
        tokens = _tokenize_query("提交PR代码")
        assert "提交" in tokens
        assert "代码" in tokens
        assert "交代" not in tokens

    def test_cjk_bigram_reduces_spurious_overlap(self) -> None:
        # "提交代码" vs "提交PR": unigram tokenization shared every char;
        # bigrams share only the leading "提交".
        commit_tokens = _tokenize_query("提交代码")
        pr_tokens = _tokenize_query("提交PR")
        assert commit_tokens & pr_tokens == {"提交"}
        assert len(commit_tokens & pr_tokens) < len(commit_tokens) / 2

    def test_mixed_text(self) -> None:
        tokens = _tokenize_query("review 代码 security 审查")
        assert "review" in tokens
        assert "security" in tokens
        assert "代码" in tokens
        assert "审查" in tokens
        assert "代" not in tokens
        assert "审" not in tokens


class TestComputeIndexScore:
    """Test index score computation."""

    def test_exact_match(self) -> None:
        profile = SkillProfile(
            skill_id="test",
            query_patterns=["review code"],
            scenarios=["code review"],
            confidence_boosters=["review"],
        )
        tokens = _tokenize_query("review code")
        score = _compute_index_score(tokens, profile)
        assert score > 0.5

    def test_no_match(self) -> None:
        profile = SkillProfile(
            skill_id="test",
            query_patterns=["deploy app"],
            scenarios=["deployment"],
        )
        tokens = _tokenize_query("review code")
        score = _compute_index_score(tokens, profile)
        assert score == 0.0

    def test_partial_match(self) -> None:
        profile = SkillProfile(
            skill_id="test",
            query_patterns=["review code quality"],
            scenarios=["security audit"],
        )
        tokens = _tokenize_query("review this code")
        score = _compute_index_score(tokens, profile)
        assert 0 < score < 1.0


class TestTryIndexLayer:
    """Test the index routing layer."""

    def test_no_index_file(self, tmp_path: Path) -> None:
        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.35

        with patch("vibesop.core.routing._layers.SkillIndexer") as MockIndexer:
            mock_indexer = MockIndexer.return_value
            mock_indexer.has_index.return_value = False
            match, detail = try_index_layer(router, "review code", [])

        assert match is None
        assert detail.matched is False
        assert "not built" in detail.reason.lower() or "index" in detail.reason.lower()

    def test_empty_index(self, tmp_path: Path) -> None:
        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.35

        # Create empty index
        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(json.dumps({"version": "1.0.0", "skills": {}}), encoding="utf-8")

        match, detail = try_index_layer(router, "review code", [])

        assert match is None
        assert detail.matched is False

    def test_index_match(self, tmp_path: Path) -> None:
        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.35
        router._get_skill_source = lambda sid, ns: "builtin"

        # Create index with a review skill
        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True)
        index_data = {
            "version": "1.0.0",
            "skills": {
                "gstack/review": {
                    "skill_id": "gstack/review",
                    "scenarios": ["code review", "PR review"],
                    "query_patterns": ["review this code", "check my PR"],
                    "differentiation": "Focus on code quality",
                    "confidence_boosters": ["review", "PR"],
                }
            },
        }
        index_path.write_text(json.dumps(index_data), encoding="utf-8")

        candidates = [{"id": "gstack/review", "description": "Review code", "namespace": "gstack"}]

        match, detail = try_index_layer(router, "review this code please", candidates)

        assert match is not None
        assert match.skill_id == "gstack/review"
        assert match.confidence >= 0.75
        assert match.metadata.get("index_hit") is True
        assert detail.matched is True
        assert "index match" in detail.reason.lower()

    def test_index_match_skill_not_in_candidates(self, tmp_path: Path) -> None:
        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.35

        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True)
        index_data = {
            "version": "1.0.0",
            "skills": {
                "gstack/review": {
                    "skill_id": "gstack/review",
                    "scenarios": ["code review"],
                    "query_patterns": ["review this code"],
                    "differentiation": "",
                    "confidence_boosters": ["review"],
                }
            },
        }
        index_path.write_text(json.dumps(index_data), encoding="utf-8")

        # No candidates match
        candidates = [{"id": "other/skill", "description": "Other"}]

        match, detail = try_index_layer(router, "review this code", candidates)

        assert match is None
        assert "not in candidates" in detail.reason.lower()


class TestEmbeddingFallback:
    """Test embedding cosine-similarity fallback when token overlap misses."""

    def test_embedding_fallback_hits_when_tokens_miss(self, tmp_path: Path) -> None:
        """Token overlap fails, but pre-computed embeddings yield a match."""
        import sys

        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.35
        router._get_skill_source = lambda sid, ns: "builtin"
        router._index_embedding_model = None  # Prevent MagicMock auto-creation

        # Profile with an embedding — query shares no tokens with profile text
        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True)
        index_data = {
            "version": "1.3.0",
            "skills": {
                "gstack/review": {
                    "skill_id": "gstack/review",
                    "scenarios": ["code review"],
                    "query_patterns": ["review this code"],
                    "differentiation": "",
                    "confidence_boosters": ["review"],
                    # Fake 3-dim embedding
                    "embedding": [1.0, 0.0, 0.0],
                }
            },
        }
        index_path.write_text(json.dumps(index_data), encoding="utf-8")

        candidates = [{"id": "gstack/review", "description": "Review code", "namespace": "gstack"}]

        # Build a fake sentence_transformers module so no real model is loaded.
        mock_model = MagicMock()
        mock_model.encode.return_value = [[0.9, 0.1, 0.0]]

        fake_st = MagicMock()
        fake_st.SentenceTransformer.return_value = mock_model

        with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
            match, detail = try_index_layer(router, "audit the authentication flow", candidates)

        assert match is not None
        assert match.skill_id == "gstack/review"
        assert match.metadata.get("embedding_match") is True
        assert detail.matched is True
        assert "embedding match" in detail.reason.lower()

    def test_no_embedding_skips_fallback(self, tmp_path: Path) -> None:
        """When the index has no embeddings, fallback is skipped gracefully."""
        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.35

        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True)
        index_data = {
            "version": "1.2.0",
            "skills": {
                "gstack/review": {
                    "skill_id": "gstack/review",
                    "scenarios": ["code review"],
                    "query_patterns": ["review this code"],
                    "differentiation": "",
                    "confidence_boosters": ["review"],
                    # No embedding field
                }
            },
        }
        index_path.write_text(json.dumps(index_data), encoding="utf-8")

        match, detail = try_index_layer(router, "audit the auth flow", [])

        assert match is None
        assert detail.matched is False
        assert "no embeddings" in detail.reason.lower()

    def test_missing_sentence_transformers_skips_fallback(self, tmp_path: Path) -> None:
        """When sentence-transformers is not installed, fallback is skipped."""
        import sys

        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.35
        router._index_embedding_model = None  # Prevent MagicMock auto-creation

        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True)
        index_data = {
            "version": "1.3.0",
            "skills": {
                "gstack/review": {
                    "skill_id": "gstack/review",
                    "scenarios": ["code review"],
                    "query_patterns": ["review this code"],
                    "differentiation": "",
                    "confidence_boosters": ["review"],
                    "embedding": [1.0, 0.0, 0.0],
                }
            },
        }
        index_path.write_text(json.dumps(index_data), encoding="utf-8")

        # Simulate sentence-transformers being uninstalled: a None entry in
        # sys.modules makes any import of the package raise ImportError,
        # regardless of whether it is actually installed in this environment.
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            match, detail = try_index_layer(router, "audit the auth flow", [])

        assert match is None
        assert detail.matched is False
        assert "not available" in detail.reason.lower()


class TestEarlyLayersRoutingPath:
    """Regression: the semantic index layer must be recorded as SEMANTIC_INDEX
    in routing_path and traces, not mislabeled as AI_TRIAGE (M1a)."""

    def _make_router(self, tmp_path: Path) -> UnifiedRouter:
        config = RoutingConfig(enable_ai_triage=False)
        return UnifiedRouter(project_root=tmp_path, config=config)

    def test_keyword_branch_records_semantic_index(self, tmp_path: Path) -> None:
        """Scenario+index best-of branch: index layer is SEMANTIC_INDEX."""
        router = self._make_router(tmp_path)
        router._tracer.enabled = True
        router._tracer.start_trace("review code")

        routing_path: list[RoutingLayer] = []
        layer_details: list[LayerDetail] = []
        scen_detail = LayerDetail(layer=RoutingLayer.SCENARIO, matched=False, reason="miss")
        idx_detail = LayerDetail(layer=RoutingLayer.SEMANTIC_INDEX, matched=False, reason="miss")

        with (
            patch(
                "vibesop.core.routing._layers.try_scenario_layer",
                return_value=(None, scen_detail),
            ),
            patch(
                "vibesop.core.routing._layers.try_index_layer",
                return_value=(None, idx_detail),
            ),
        ):
            router._try_early_layers("review code", [], routing_path, layer_details, use_keyword=True)

        assert routing_path == [RoutingLayer.SCENARIO, RoutingLayer.SEMANTIC_INDEX]
        assert RoutingLayer.AI_TRIAGE not in routing_path
        traced = [lt.layer for lt in router._tracer._current.layers]  # type: ignore[union-attr]
        assert traced == ["scenario", "semantic_index"]

    def test_llm_branch_records_semantic_index(self, tmp_path: Path) -> None:
        """Index-standalone branch: index layer is SEMANTIC_INDEX."""
        router = self._make_router(tmp_path)
        router._tracer.enabled = True
        router._tracer.start_trace("review code")

        routing_path: list[RoutingLayer] = []
        layer_details: list[LayerDetail] = []
        idx_detail = LayerDetail(layer=RoutingLayer.SEMANTIC_INDEX, matched=False, reason="miss")

        with patch(
            "vibesop.core.routing._layers.try_index_layer",
            return_value=(None, idx_detail),
        ):
            router._try_early_layers("review code", [], routing_path, layer_details, use_keyword=False)

        assert routing_path == [RoutingLayer.SEMANTIC_INDEX]
        assert RoutingLayer.AI_TRIAGE not in routing_path
        traced = [lt.layer for lt in router._tracer._current.layers]  # type: ignore[union-attr]
        assert traced == ["semantic_index"]
