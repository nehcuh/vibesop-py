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
        index_path.write_text(json.dumps({"version": "1.0.0", "skills": {}}))

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
        index_path.write_text(json.dumps(index_data))

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
        index_path.write_text(json.dumps(index_data))

        # No candidates match
        candidates = [{"id": "other/skill", "description": "Other"}]

        match, detail = try_index_layer(router, "review this code", candidates)

        assert match is None
        assert "not in candidates" in detail.reason.lower()
