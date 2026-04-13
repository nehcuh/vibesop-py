"""Tests for InstinctLearner semantic matching upgrades."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vibesop.core.instinct.learner import InstinctLearner


class TestInstinctLearnerMatchScore:
    """Test suite for InstinctLearner._match_score."""

    def test_match_score_lexical_exact_match(self) -> None:
        """Lexical path should score exact word overlap highly."""
        learner = InstinctLearner()
        score = learner._match_score("debug error", "debug this error")
        assert score > 0.5

    def test_match_score_lexical_no_overlap(self) -> None:
        """Lexical path should score unrelated texts lowly."""
        learner = InstinctLearner()
        score = learner._match_score("database migration", "frontend styling")
        assert score < 0.3

    def test_match_score_embedding_boost(self, monkeypatch) -> None:
        """When embeddings are available, semantic similarity should boost score."""
        learner = InstinctLearner()
        # Mock numpy available
        mock_np = MagicMock()
        mock_np.dot.return_value = 0.85
        mock_np.linalg.norm.return_value = 1.0
        learner._numpy = mock_np

        fake_model = MagicMock()
        fake_model.encode.return_value = [MagicMock()]
        learner._embedding_model = fake_model

        # Mock _compute_embedding_similarity to return high semantic score
        monkeypatch.setattr(learner, "_compute_embedding_similarity", lambda p, t: 0.82)

        # Pattern with low lexical overlap but high semantic similarity
        score = learner._match_score("fix bug", "debug failure")
        # max(lexical, 0.82) should be ~0.82
        assert score == pytest.approx(0.82, abs=0.01)

    def test_match_score_fallback_when_embedding_unavailable(self) -> None:
        """When numpy is missing, should fall back to lexical score."""
        learner = InstinctLearner()
        learner._numpy = None
        learner._embedding_model = None

        score = learner._match_score("refactor code", "clean up code")
        # Should still get a reasonable lexical score
        assert score > 0.3

    def test_match_score_embedding_exception_falls_back(self, monkeypatch) -> None:
        """If embedding computation raises, should still return lexical score."""
        learner = InstinctLearner()
        learner._numpy = MagicMock()
        learner._embedding_model = MagicMock()

        def _raise(*_a, **_k):
            raise RuntimeError("model failure")

        monkeypatch.setattr(learner, "_compute_embedding_similarity", _raise)

        score = learner._match_score("test code", "write tests")
        assert score >= 0.0  # lexical fallback works


class TestInstinctLearnerEmbeddingInfrastructure:
    """Test embedding model initialization and caching."""

    def test_embedding_enabled_false_without_numpy(self) -> None:
        learner = InstinctLearner()
        learner._numpy = None
        assert learner._embedding_enabled() is False

    def test_embedding_enabled_true_with_mock_model(self) -> None:
        learner = InstinctLearner()
        learner._numpy = MagicMock()
        learner._embedding_model = MagicMock()
        assert learner._embedding_enabled() is True

    def test_embedding_enabled_imports_model_lazily(self, monkeypatch) -> None:
        learner = InstinctLearner()
        learner._numpy = MagicMock()
        learner._embedding_model = None

        fake_st = MagicMock()
        fake_st.SentenceTransformer.return_value = MagicMock()
        monkeypatch.setitem(
            __import__("sys").modules, "sentence_transformers", fake_st
        )

        assert learner._embedding_enabled() is True
        assert learner._embedding_model is not None

    def test_get_embedding_caches_results(self) -> None:
        learner = InstinctLearner()
        learner._numpy = MagicMock()
        fake_model = MagicMock()
        fake_emb = MagicMock()
        fake_model.encode.return_value = [fake_emb]
        learner._embedding_model = fake_model

        emb1 = learner._get_embedding("hello")
        emb2 = learner._get_embedding("hello")
        assert emb1 is emb2
        fake_model.encode.assert_called_once()

    def test_embedding_cache_cleared_on_learn(self) -> None:
        learner = InstinctLearner()
        learner._numpy = MagicMock()
        fake_model = MagicMock()
        fake_model.encode.return_value = [MagicMock()]
        learner._embedding_model = fake_model

        learner._get_embedding("pattern")
        assert "pattern" in learner._embedding_cache

        learner.learn("new pattern", "action")
        assert "pattern" not in learner._embedding_cache

    def test_embedding_cache_cleared_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / "instincts.jsonl"
            storage.write_text(
                '{"id":"i1","pattern":"p1","action":"a1","created_at":"2024-01-01T00:00:00"}\n'
            )
            learner = InstinctLearner(storage_path=storage)
            learner._numpy = MagicMock()
            fake_model = MagicMock()
            fake_model.encode.return_value = [MagicMock()]
            learner._embedding_model = fake_model

            learner._get_embedding("p1")
            assert "p1" in learner._embedding_cache

            # Re-loading from storage should clear cache
            learner._load()
            assert "p1" not in learner._embedding_cache


class TestInstinctLearnerSemanticMatching:
    """Integration-style tests for find_matching with semantic similarity."""

    def test_find_matching_uses_embedding_semantics(self, monkeypatch) -> None:
        """If embeddings available, semantically related queries should match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            learner = InstinctLearner(storage_path=Path(tmpdir) / "instincts.jsonl")
            # Pre-seed a reliable instinct
            instinct = learner.learn("debug code", "suggest systematic-debugging")
            instinct.success_count = 5
            instinct.failure_count = 1
            learner._save()

            # Mock embedding to return high similarity for semantically related query
            def _mock_sim(pattern: str, text: str) -> float:
                # Simulate that "debug code" is semantically similar to "fix error"
                if pattern == "debug code" and text == "fix error":
                    return 0.75
                return 0.0

            monkeypatch.setattr(learner, "_compute_embedding_similarity", _mock_sim)
            learner._numpy = MagicMock()
            learner._embedding_model = MagicMock()

            matches = learner.find_matching("fix error", min_confidence=0.5)
            assert len(matches) == 1
            assert matches[0].pattern == "debug code"

    def test_find_matching_falls_back_to_lexical(self) -> None:
        """Without embeddings, exact word overlap still works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            learner = InstinctLearner(storage_path=Path(tmpdir) / "instincts.jsonl")
            learner._numpy = None
            learner._embedding_model = None

            instinct = learner.learn("refactor legacy code", "suggest superpowers/refactor")
            instinct.success_count = 4
            instinct.failure_count = 0
            learner._save()

            matches = learner.find_matching("refactor this legacy code")
            assert len(matches) == 1
            assert matches[0].pattern == "refactor legacy code"
