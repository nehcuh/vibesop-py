"""Tests for the skill semantic index routing layer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        assert "帮" in tokens
        assert "审" in tokens
        assert "查" in tokens
        assert "代" in tokens
        assert "码" in tokens

    def test_mixed_text(self) -> None:
        tokens = _tokenize_query("review 代码 security 审查")
        assert "review" in tokens
        assert "security" in tokens
        assert "代" in tokens
        assert "审" in tokens


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

        # Ensure sentence_transformers is NOT importable by removing any mock
        # that earlier tests may have injected into sys.modules.
        _saved = sys.modules.pop("sentence_transformers", None)
        try:
            match, detail = try_index_layer(router, "audit the auth flow", [])
        finally:
            if _saved is not None:
                sys.modules["sentence_transformers"] = _saved

        assert match is None
        assert detail.matched is False
        assert "not available" in detail.reason.lower()
