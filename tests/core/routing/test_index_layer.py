"""Tests for the skill semantic index routing layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar
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
        """Stale profiles (skill no longer installed) are skipped up front.

        Pre-M9-fix the token loop let a stale profile win and then hard-miss
        at the candidate check WITHOUT trying the embedding fallback. Now the
        loop is installed-only, so this query misses the token path and the
        (here: embedding-less) fallback produces the final detail instead of
        the dead "not in candidates" short-circuit.
        """
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
        assert detail.matched is False
        assert "not in candidates" not in detail.reason.lower()


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
            router._try_early_layers(
                "review code", [], routing_path, layer_details, use_keyword=True
            )

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
            router._try_early_layers(
                "review code", [], routing_path, layer_details, use_keyword=False
            )

        assert routing_path == [RoutingLayer.SEMANTIC_INDEX]
        assert RoutingLayer.AI_TRIAGE not in routing_path
        traced = [lt.layer for lt in router._tracer._current.layers]  # type: ignore[union-attr]
        assert traced == ["semantic_index"]


class TestIndexLayerGuardedSkills:
    """Guarded skills (session-end, riper-workflow) must not win the index
    layer on token overlap or embedding similarity alone — they require an
    explicit signal in the query (same criterion as the AI-triage guard).

    Regression: 「似乎有其他进程没有关闭，帮我先关闭了」 embedded closest to
    builtin/session-end (similarity 0.52) without any exit intent.
    """

    @staticmethod
    def _guard_all(_query: str, _candidates: list, _skill_id: str) -> bool:
        return False

    @staticmethod
    def _allow_all(_query: str, _candidates: list, _skill_id: str) -> bool:
        return True

    def _router(self, tmp_path: Path, guard) -> MagicMock:
        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.35
        router._get_skill_source = lambda sid, ns: "builtin"
        router._index_embedding_model = None  # Prevent MagicMock auto-creation
        router._triage_service = MagicMock()
        router._triage_service.has_explicit_guard_signal = guard
        return router

    def _write_session_end_index(self, tmp_path: Path, **extra: object) -> None:
        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        profile = {
            "skill_id": "builtin/session-end",
            "scenarios": ["wrap up session"],
            "query_patterns": ["收工 总结 会话"],
            "differentiation": "",
            "confidence_boosters": ["会话", "总结"],
            **extra,
        }
        index_path.write_text(
            json.dumps({"version": "1.3.0", "skills": {"builtin/session-end": profile}}),
            encoding="utf-8",
        )

    def test_token_match_on_guarded_skill_without_signal_abstains(self, tmp_path: Path) -> None:
        self._write_session_end_index(tmp_path)
        router = self._router(tmp_path, self._guard_all)
        candidates = [
            {"id": "builtin/session-end", "description": "Wrap up", "namespace": "builtin"}
        ]

        match, detail = try_index_layer(router, "收工 总结 会话 记录", candidates)

        assert match is None
        assert detail.matched is False
        assert "guarded" in detail.reason.lower()

    def test_token_match_on_guarded_skill_with_signal_passes(self, tmp_path: Path) -> None:
        self._write_session_end_index(tmp_path)
        router = self._router(tmp_path, self._allow_all)
        candidates = [
            {"id": "builtin/session-end", "description": "Wrap up", "namespace": "builtin"}
        ]

        match, detail = try_index_layer(router, "收工 总结 会话 记录", candidates)

        assert match is not None
        assert match.skill_id == "builtin/session-end"
        assert detail.matched is True

    def test_embedding_match_on_guarded_skill_without_signal_abstains(self, tmp_path: Path) -> None:
        import sys

        self._write_session_end_index(tmp_path, embedding=[1.0, 0.0, 0.0])
        router = self._router(tmp_path, self._guard_all)
        candidates = [
            {"id": "builtin/session-end", "description": "Wrap up", "namespace": "builtin"}
        ]

        mock_model = MagicMock()
        mock_model.encode.return_value = [[0.9, 0.1, 0.0]]
        fake_st = MagicMock()
        fake_st.SentenceTransformer.return_value = mock_model

        with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
            # Query shares no tokens with the profile → token path misses and
            # the embedding fallback runs.
            match, detail = try_index_layer(router, "zz qq xx", candidates)

        assert match is None
        assert detail.matched is False
        assert "guarded" in detail.reason.lower()


class TestExternalTokenThreshold:
    """External pack profiles must clear a higher token-overlap bar.

    Pack profiles are LLM-generated per installed pack (dozens at a time,
    with heavily overlapping vocabulary), so a marginal bigram overlap with
    a pack profile is much weaker evidence than the same overlap with a
    curated builtin/project profile. The layer applies
    ``index_external_match_threshold`` to non-builtin/non-project skills.
    """

    _PROFILE_TEXT: ClassVar[dict[str, object]] = {
        "scenarios": ["deploy release candidate build"],
        "query_patterns": [
            "publish staging artifact bundle",
            "rollout production hotfix pipeline",
            "tag version changelog draft",
        ],
        "differentiation": "",
        "confidence_boosters": [],
    }
    # Profile token pool = scenarios + query_patterns + confidence_boosters
    # (differentiation is NOT indexed) = 16 unique tokens.
    # Overlap {deploy, release} = 2 / max(3, 16 * 0.5) = 0.25 — above the
    # 0.20 builtin bar, below the 0.30 external bar.
    _WEAK_QUERY = "deploy release notes"
    _STRONG_QUERY = "deploy release candidate build publish staging"

    def _router(self, tmp_path: Path, external_threshold: object = None) -> MagicMock:
        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.20
        if external_threshold is not None:
            router._config.index_external_match_threshold = external_threshold
        router._get_skill_source = lambda sid, ns: ns
        router._index_embedding_model = None  # Prevent MagicMock auto-creation
        return router

    def _write_index(self, tmp_path: Path, skill_ids: list[str]) -> None:
        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        profiles = {sid: {"skill_id": sid, **self._PROFILE_TEXT} for sid in skill_ids}
        index_path.write_text(
            json.dumps({"version": "1.3.0", "skills": profiles}), encoding="utf-8"
        )

    def test_weak_overlap_matches_builtin_but_not_external(self, tmp_path: Path) -> None:
        """Same profile text, same weak overlap: builtin wins, pack abstains."""
        self._write_index(tmp_path, ["acme-pack/ship-release", "builtin/ship-release"])
        router = self._router(tmp_path)
        candidates = [
            {"id": "acme-pack/ship-release", "description": "d", "namespace": "acme-pack"},
            {"id": "builtin/ship-release", "description": "d", "namespace": "builtin"},
        ]

        match, detail = try_index_layer(router, self._WEAK_QUERY, candidates)

        assert match is not None
        assert match.skill_id == "builtin/ship-release"
        assert detail.matched is True

    def test_weak_overlap_external_only_abstains(self, tmp_path: Path) -> None:
        """A weak overlap that would match a builtin profile is rejected for packs."""
        self._write_index(tmp_path, ["acme-pack/ship-release"])
        router = self._router(tmp_path)
        candidates = [
            {"id": "acme-pack/ship-release", "description": "d", "namespace": "acme-pack"},
        ]

        match, detail = try_index_layer(router, self._WEAK_QUERY, candidates)

        assert match is None
        assert detail.matched is False

    def test_strong_overlap_external_still_matches(self, tmp_path: Path) -> None:
        """The higher bar does not block genuinely strong pack matches."""
        self._write_index(tmp_path, ["acme-pack/ship-release"])
        router = self._router(tmp_path)
        candidates = [
            {"id": "acme-pack/ship-release", "description": "d", "namespace": "acme-pack"},
        ]

        match, detail = try_index_layer(router, self._STRONG_QUERY, candidates)

        assert match is not None
        assert match.skill_id == "acme-pack/ship-release"
        assert detail.matched is True

    def test_external_threshold_is_configurable(self, tmp_path: Path) -> None:
        """Lowering the external bar below the weak score re-admits the pack."""
        self._write_index(tmp_path, ["acme-pack/ship-release"])
        router = self._router(tmp_path, external_threshold=0.10)
        candidates = [
            {"id": "acme-pack/ship-release", "description": "d", "namespace": "acme-pack"},
        ]

        match, detail = try_index_layer(router, self._WEAK_QUERY, candidates)

        assert match is not None
        assert match.skill_id == "acme-pack/ship-release"
        assert detail.matched is True


class TestEmbeddingMargin:
    """Embedding fallback requires a clear top1-minus-top2 gap.

    The fallback is an argmax over the whole profile catalog; with many
    LLM-generated profiles installed, the nearest profile of an unrelated
    query lands in the model's noise band just above the absolute threshold.
    Genuine intent separates from the runner-up; noise does not.
    """

    def _router(self, tmp_path: Path, margin: object = None) -> MagicMock:
        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.35
        if margin is not None:
            router._config.index_embedding_min_margin = margin
        router._get_skill_source = lambda sid, ns: ns
        router._index_embedding_model = None  # Prevent MagicMock auto-creation
        router._triage_service = MagicMock()
        router._triage_service.has_explicit_guard_signal = lambda q, c, s: True
        return router

    @staticmethod
    def _write_index(tmp_path: Path, profiles: dict[str, list[float]]) -> None:
        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps(
                {
                    "version": "1.3.0",
                    "skills": {
                        sid: {
                            "skill_id": sid,
                            "scenarios": ["unrelated scenario text"],
                            "query_patterns": ["unrelated query pattern"],
                            "differentiation": "",
                            "confidence_boosters": [],
                            "embedding": emb,
                        }
                        for sid, emb in profiles.items()
                    },
                }
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _fake_model(vector: list[float]) -> MagicMock:
        mock_model = MagicMock()
        mock_model.encode.return_value = [vector]
        fake_st = MagicMock()
        fake_st.SentenceTransformer.return_value = mock_model
        return fake_st

    def test_close_runner_up_abstains(self, tmp_path: Path) -> None:
        """Top-1 barely ahead of top-2 → treated as catalog noise."""
        import sys

        self._write_index(
            tmp_path,
            {
                "acme-pack/alpha": [1.0, 0.0, 0.0],
                "acme-pack/beta": [0.999, 0.04, 0.0],
            },
        )
        router = self._router(tmp_path)
        candidates = [
            {"id": "acme-pack/alpha", "description": "d", "namespace": "acme-pack"},
            {"id": "acme-pack/beta", "description": "d", "namespace": "acme-pack"},
        ]

        # Token-disjoint query so the token path misses and the fallback runs.
        with patch.dict(sys.modules, {"sentence_transformers": self._fake_model([1.0, 0.0, 0.0])}):
            match, detail = try_index_layer(router, "zq wv xk", candidates)

        assert match is None
        assert detail.matched is False
        assert "margin" in detail.reason.lower()

    def test_clear_gap_matches(self, tmp_path: Path) -> None:
        """Top-1 far ahead of top-2 → accepted."""
        import sys

        self._write_index(
            tmp_path,
            {
                "acme-pack/alpha": [1.0, 0.0, 0.0],
                "acme-pack/beta": [0.0, 1.0, 0.0],
            },
        )
        router = self._router(tmp_path)
        candidates = [
            {"id": "acme-pack/alpha", "description": "d", "namespace": "acme-pack"},
            {"id": "acme-pack/beta", "description": "d", "namespace": "acme-pack"},
        ]

        with patch.dict(sys.modules, {"sentence_transformers": self._fake_model([1.0, 0.0, 0.0])}):
            match, _detail = try_index_layer(router, "zq wv xk", candidates)

        assert match is not None
        assert match.skill_id == "acme-pack/alpha"
        assert match.metadata.get("embedding_match") is True

    def test_margin_check_disabled_at_zero(self, tmp_path: Path) -> None:
        """index_embedding_min_margin = 0 restores pure argmax behavior."""
        import sys

        self._write_index(
            tmp_path,
            {
                "acme-pack/alpha": [1.0, 0.0, 0.0],
                "acme-pack/beta": [0.999, 0.04, 0.0],
            },
        )
        router = self._router(tmp_path, margin=0.0)
        candidates = [
            {"id": "acme-pack/alpha", "description": "d", "namespace": "acme-pack"},
            {"id": "acme-pack/beta", "description": "d", "namespace": "acme-pack"},
        ]

        with patch.dict(sys.modules, {"sentence_transformers": self._fake_model([1.0, 0.0, 0.0])}):
            match, _detail = try_index_layer(router, "zq wv xk", candidates)

        assert match is not None
        assert match.skill_id == "acme-pack/alpha"

    def test_uninstalled_profile_excluded_from_ranking(self, tmp_path: Path) -> None:
        """A stale profile for an uninstalled skill must not win or eat the margin."""
        import sys

        self._write_index(
            tmp_path,
            {
                "gone-pack/removed-skill": [1.0, 0.0, 0.0],  # not installed
                "acme-pack/alpha": [0.9, 0.1, 0.0],
            },
        )
        router = self._router(tmp_path)
        candidates = [
            {"id": "acme-pack/alpha", "description": "d", "namespace": "acme-pack"},
        ]

        with patch.dict(sys.modules, {"sentence_transformers": self._fake_model([1.0, 0.0, 0.0])}):
            match, _detail = try_index_layer(router, "zq wv xk", candidates)

        assert match is not None
        assert match.skill_id == "acme-pack/alpha"


class TestStaleProfilePreemption:
    """Installed-only invariant, token path: a stale profile (skill no longer
    installed) must not win the token match and thereby pre-empt the
    embedding fallback, which ranks installed candidates only."""

    def test_stale_token_hit_does_not_block_installed_embedding_match(self, tmp_path: Path) -> None:
        import sys

        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.20
        router._get_skill_source = lambda sid, ns: ns
        router._index_embedding_model = None  # Prevent MagicMock auto-creation
        router._triage_service = MagicMock()
        router._triage_service.has_explicit_guard_signal = lambda q, c, s: True

        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps(
                {
                    "version": "1.3.0",
                    "skills": {
                        # Stale: NOT installed. Token overlap with the query
                        # is total (score 1.0) — it would always win the
                        # token race if it were allowed to compete.
                        "gone-pack/stale-skill": {
                            "skill_id": "gone-pack/stale-skill",
                            "scenarios": ["archive the quarterly report"],
                            "query_patterns": ["archive the quarterly report"],
                            "differentiation": "",
                            "confidence_boosters": [],
                        },
                        # Installed: token-disjoint, embedding-matched.
                        "acme-pack/real-skill": {
                            "skill_id": "acme-pack/real-skill",
                            "scenarios": ["unrelated potato gardening"],
                            "query_patterns": ["unrelated potato gardening"],
                            "differentiation": "",
                            "confidence_boosters": [],
                            "embedding": [1.0, 0.0, 0.0],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        candidates = [
            {"id": "acme-pack/real-skill", "description": "d", "namespace": "acme-pack"},
        ]

        mock_model = MagicMock()
        mock_model.encode.return_value = [[1.0, 0.0, 0.0]]
        fake_st = MagicMock()
        fake_st.SentenceTransformer.return_value = mock_model

        with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
            match, _detail = try_index_layer(router, "archive the quarterly report", candidates)

        assert match is not None
        assert match.skill_id == "acme-pack/real-skill"
        assert match.metadata.get("embedding_match") is True


class TestTrustedNamespaceCoverage:
    """The trusted bar applies to every repo/project-curated namespace,
    including the "custom"/"cross-cutting" namespaces the project-local
    .vibe/skills entries declare in their frontmatter."""

    _PROFILE_TEXT: ClassVar[dict[str, object]] = {
        "scenarios": ["deploy release candidate build"],
        "query_patterns": [
            "publish staging artifact bundle",
            "rollout production hotfix pipeline",
            "tag version changelog draft",
        ],
        "differentiation": "",
        "confidence_boosters": [],
    }
    # Overlap {deploy, release} = 2 / max(3, 16 * 0.5) = 0.25 — above the
    # 0.20 trusted bar, below the 0.30 external bar.
    _WEAK_QUERY = "deploy release notes"

    def _router(self, tmp_path: Path, bare_config: bool = False) -> MagicMock:
        router = MagicMock()
        router.project_root = tmp_path
        if not bare_config:
            router._config.index_match_threshold = 0.20
        router._get_skill_source = lambda sid, ns: ns
        router._index_embedding_model = None  # Prevent MagicMock auto-creation
        return router

    def _write_index(self, tmp_path: Path, skill_id: str) -> None:
        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps(
                {
                    "version": "1.3.0",
                    "skills": {skill_id: {"skill_id": skill_id, **self._PROFILE_TEXT}},
                }
            ),
            encoding="utf-8",
        )

    def test_custom_namespace_gets_trusted_bar(self, tmp_path: Path) -> None:
        self._write_index(tmp_path, "custom/ship-release")
        router = self._router(tmp_path)
        candidates = [
            {"id": "custom/ship-release", "description": "d", "namespace": "custom"},
        ]

        match, _detail = try_index_layer(router, self._WEAK_QUERY, candidates)

        assert match is not None
        assert match.skill_id == "custom/ship-release"

    def test_cross_cutting_namespace_gets_trusted_bar(self, tmp_path: Path) -> None:
        self._write_index(tmp_path, "cross-cutting/ship-release")
        router = self._router(tmp_path)
        candidates = [
            {"id": "cross-cutting/ship-release", "description": "d", "namespace": "cross-cutting"},
        ]

        match, _detail = try_index_layer(router, self._WEAK_QUERY, candidates)

        assert match is not None
        assert match.skill_id == "cross-cutting/ship-release"

    def test_unset_config_knobs_fall_back_to_field_defaults(self, tmp_path: Path) -> None:
        """A bare MagicMock config (no knob set) must behave as the declared
        RoutingConfig defaults: 0.20 trusted bar, 0.30 external bar."""
        self._write_index(tmp_path, "acme-pack/ship-release")
        router = self._router(tmp_path, bare_config=True)
        candidates = [
            {"id": "acme-pack/ship-release", "description": "d", "namespace": "acme-pack"},
        ]

        match, detail = try_index_layer(router, self._WEAK_QUERY, candidates)

        # 0.25 clears the 0.20 default trusted bar but not the 0.30 default
        # external bar → abstain.
        assert match is None
        assert detail.matched is False


class TestEmbeddingThresholdKnob:
    """index_embedding_threshold is a config field like its neighbors."""

    def test_raised_threshold_rejects_match(self, tmp_path: Path) -> None:
        import sys

        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.35
        router._config.index_embedding_threshold = 0.99
        router._get_skill_source = lambda sid, ns: ns
        router._index_embedding_model = None  # Prevent MagicMock auto-creation
        router._triage_service = MagicMock()
        router._triage_service.has_explicit_guard_signal = lambda q, c, s: True

        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps(
                {
                    "version": "1.3.0",
                    "skills": {
                        "acme-pack/alpha": {
                            "skill_id": "acme-pack/alpha",
                            "scenarios": ["unrelated scenario text"],
                            "query_patterns": ["unrelated query pattern"],
                            "differentiation": "",
                            "confidence_boosters": [],
                            "embedding": [1.0, 0.0, 0.0],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        candidates = [
            {"id": "acme-pack/alpha", "description": "d", "namespace": "acme-pack"},
        ]

        mock_model = MagicMock()
        # sim([0.7, 0.7, 0], [1, 0, 0]) ≈ 0.707 — above the 0.45 default but
        # below the raised 0.99 knob.
        mock_model.encode.return_value = [[0.7, 0.7, 0.0]]
        fake_st = MagicMock()
        fake_st.SentenceTransformer.return_value = mock_model

        with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
            match, detail = try_index_layer(router, "zq wv xk", candidates)

        assert match is None
        assert detail.matched is False
        assert "threshold" in detail.reason.lower()
