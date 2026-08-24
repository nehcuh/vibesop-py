"""Tests for EmbeddingRecall and its integration into the triage prefilter."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

from vibesop.core.routing.triage_recall import (
    DEFAULT_MIN_SIMILARITY,
    MODEL_NAME,
    EmbeddingRecall,
    _cosine_similarity,
)
from vibesop.core.routing.triage_service import TriageService
from vibesop.utils import file_lock
from vibesop.utils.file_lock import CouldNotLock


class _FakeModel:
    """Deterministic stand-in for SentenceTransformer (no download)."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors
        self.encoded_texts: list[str] = []

    def encode(self, texts: list[str], show_progress_bar: bool = False) -> list[list[float]]:
        self.encoded_texts.extend(texts)
        return [self.vectors[t] for t in texts]


def _candidates() -> list[dict[str, Any]]:
    return [
        {"id": "deploy", "description": "deploy services to production"},
        {"id": "debug", "description": "debug failing tests"},
        {"id": "review", "description": "review code changes"},
    ]


def _make_recall(
    tmp_path: Any,
    query_vector: list[float],
    min_similarity: float = 0.0,
) -> tuple[EmbeddingRecall, _FakeModel]:
    """Recall with a fake model: query aligned with 'deploy', others orthogonal.

    ``min_similarity`` defaults to 0.0 so the pre-threshold ranking behavior
    of the existing tests is preserved (orthogonal candidates score 0.0).
    """
    recall = EmbeddingRecall(tmp_path, min_similarity=min_similarity)
    vectors = {"ship it": query_vector}
    for c in _candidates():
        text = EmbeddingRecall._candidate_text(c)
        # 'deploy' closest to the query, the rest spread out orthogonally
        vectors[text] = {
            "deploy": [0.9, 0.1, 0.0],
            "debug": [0.0, 1.0, 0.0],
            "review": [0.0, 0.0, 1.0],
        }[str(c["id"])]
    model = _FakeModel(vectors)
    recall._model = model
    return recall, model


class TestEmbeddingRecall:
    """Test EmbeddingRecall.recall ranking and degradation."""

    def test_recall_ranks_by_similarity(self, tmp_path: Any) -> None:
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        result = recall.recall("ship it", _candidates(), 2)
        assert result == ["deploy", "debug"]

    def test_recall_none_when_model_unavailable(self, tmp_path: Any) -> None:
        recall = EmbeddingRecall(tmp_path)
        recall._model_failed = True
        assert recall.recall("ship it", _candidates(), 2) is None

    def test_model_load_failure_is_sticky(self, tmp_path: Any) -> None:
        recall = EmbeddingRecall(tmp_path)
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            assert recall._get_model() is None
        # A later call must not retry the import.
        assert recall._get_model() is None

    def test_recall_none_on_encode_error(self, tmp_path: Any) -> None:
        recall = EmbeddingRecall(tmp_path)
        model = _FakeModel({})
        recall._model = model
        # Unknown texts -> KeyError inside encode -> fail open.
        assert recall.recall("ship it", _candidates(), 2) is None


class TestRecallMinSimilarity:
    """Similarity floor: junk queries must not flood the LLM triage window."""

    def test_default_threshold_is_set(self, tmp_path: Any) -> None:
        assert EmbeddingRecall(tmp_path).min_similarity == DEFAULT_MIN_SIMILARITY

    def test_below_threshold_candidates_dropped(self, tmp_path: Any) -> None:
        # query ~0.99 similar to 'deploy', orthogonal (0.0) to the rest.
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0], min_similarity=0.5)
        assert recall.recall("ship it", _candidates(), 3) == ["deploy"]

    def test_threshold_boundary_is_inclusive(self, tmp_path: Any) -> None:
        """A candidate scoring exactly ``min_similarity`` is kept (>=)."""
        candidates = [{"id": "edge", "description": "edge case"}]
        query_vec = [1.0, 0.0]
        candidate_vec = [1.0, 3**0.5]  # cosine vs query_vec ≈ 0.5
        floor = _cosine_similarity(query_vec, candidate_vec)
        text = EmbeddingRecall._candidate_text(candidates[0])
        recall = EmbeddingRecall(tmp_path, min_similarity=floor)
        recall._model = _FakeModel({"q": query_vec, text: candidate_vec})
        assert recall.recall("q", candidates, 1) == ["edge"]
        # Just above the floor: dropped.
        recall.min_similarity = floor + 1e-9
        assert recall.recall("q", candidates, 1) == []

    def test_all_below_threshold_returns_empty_list_not_none(self, tmp_path: Any) -> None:
        """Empty list = recall ran, nothing relevant; None = recall
        unavailable (keyword fallback). The distinction matters to the caller."""
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0], min_similarity=0.999)
        result = recall.recall("ship it", _candidates(), 2)
        assert result == []


class TestEmbeddingCache:
    """Test persistence: content-hash invalidation, corruption, locking."""

    def test_cache_written_and_reused(self, tmp_path: Any) -> None:
        recall, model = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        recall.recall("ship it", _candidates(), 2)
        cache_path = tmp_path / "skill_embeddings.json"
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert set(data) == {"deploy", "debug", "review"}
        first_ts = data["deploy"]["ts"]
        encoded_after_first = len(model.encoded_texts)

        # Second run with unchanged candidates: nothing re-encoded.
        recall2, model2 = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        result = recall2.recall("ship it", _candidates(), 2)
        assert result == ["deploy", "debug"]
        assert model2.encoded_texts == ["ship it"]  # query only
        assert len(model.encoded_texts) == encoded_after_first
        assert json.loads(cache_path.read_text(encoding="utf-8"))["deploy"]["ts"] == first_ts

    def test_content_hash_change_reencodes(self, tmp_path: Any) -> None:
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        recall.recall("ship it", _candidates(), 2)

        changed = _candidates()
        changed[1] = {"id": "debug", "description": "trace production incidents"}
        recall2, model2 = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        # New description is unknown to the fake model -> add its vector.
        model2.vectors[EmbeddingRecall._candidate_text(changed[1])] = [0.0, 1.0, 0.0]
        recall2._model = model2
        result = recall2.recall("ship it", changed, 2)
        assert result == ["deploy", "debug"]
        # Query + exactly the one changed candidate were encoded.
        assert model2.encoded_texts == [
            EmbeddingRecall._candidate_text(changed[1]),
            "ship it",
        ]
        data = json.loads((tmp_path / "skill_embeddings.json").read_text(encoding="utf-8"))
        assert data["debug"]["embedding"] == [0.0, 1.0, 0.0]

    def test_model_mismatch_reencodes(self, tmp_path: Any) -> None:
        """Vectors are model-specific: a MODEL_NAME change invalidates the cache."""
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        recall.recall("ship it", _candidates(), 2)
        cache_path = tmp_path / "skill_embeddings.json"
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert data["deploy"]["model"] == MODEL_NAME

        # Switching the embedding model must re-encode every candidate.
        with patch("vibesop.core.routing.triage_recall.MODEL_NAME", "other-model"):
            recall2, model2 = _make_recall(tmp_path, [1.0, 0.0, 0.0])
            result = recall2.recall("ship it", _candidates(), 2)
            assert result == ["deploy", "debug"]
            candidate_texts = {EmbeddingRecall._candidate_text(c) for c in _candidates()}
            assert candidate_texts <= set(model2.encoded_texts)
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            assert all(entry["model"] == "other-model" for entry in data.values())

    def test_corrupt_cache_self_heals(self, tmp_path: Any) -> None:
        cache_path = tmp_path / "skill_embeddings.json"
        cache_path.write_text("not json{{{", encoding="utf-8")
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        result = recall.recall("ship it", _candidates(), 2)
        assert result == ["deploy", "debug"]
        # File was rewritten as valid JSON.
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert "deploy" in data

    def test_lock_contention_degrades_gracefully(self, tmp_path: Any) -> None:
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        with patch(
            "vibesop.utils.file_lock.cross_process_lock",
            side_effect=CouldNotLock("held"),
        ):
            result = recall.recall("ship it", _candidates(), 2)
        # Recall still works from a fresh in-memory encode; nothing persisted.
        assert result == ["deploy", "debug"]
        assert not (tmp_path / "skill_embeddings.json").exists()

    def test_read_modify_write_uses_single_lock(self, tmp_path: Any) -> None:
        """The cache read-modify-write runs in one critical section — a
        split read/write would lose entries written concurrently."""
        acquisitions = 0
        real_lock = file_lock.cross_process_lock

        @contextmanager
        def counting_lock(*args: Any, **kwargs: Any):
            nonlocal acquisitions
            acquisitions += 1
            with real_lock(*args, **kwargs):
                yield

        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        with patch(
            "vibesop.utils.file_lock.cross_process_lock",
            side_effect=counting_lock,
        ):
            assert recall.recall("ship it", _candidates(), 2) == ["deploy", "debug"]
        assert acquisitions == 1
        data = json.loads((tmp_path / "skill_embeddings.json").read_text(encoding="utf-8"))
        assert set(data) == {"deploy", "debug", "review"}

    def test_concurrent_recalls_never_lose_entries(self, tmp_path: Any) -> None:
        """Two recalls racing on the same cache: the loser of the
        non-blocking lock degrades to an in-memory encode (no write), so
        the winner's entries are never clobbered, and a follow-up recall
        converges to the full candidate set."""
        barrier = threading.Barrier(2)
        results: list[list[str] | None] = [None, None]

        def run(index: int, candidates: list[dict[str, Any]]) -> None:
            recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
            barrier.wait()
            results[index] = recall.recall("ship it", candidates, 2)

        threads = [
            threading.Thread(target=run, args=(0, _candidates()[:2])),
            threading.Thread(target=run, args=(1, _candidates()[1:])),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results[0] == ["deploy", "debug"]
        assert results[1] == ["debug", "review"]

        # Whatever the interleaving, the cache file stays valid JSON and a
        # follow-up recall self-heals to the full candidate set.
        cache_path = tmp_path / "skill_embeddings.json"
        recall3, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        assert recall3.recall("ship it", _candidates(), 2) == ["deploy", "debug"]
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert set(data) == {"deploy", "debug", "review"}

    def test_uninstalled_skill_entries_pruned(self, tmp_path: Any) -> None:
        """Entries for skills no longer among the candidates are pruned on
        write instead of lingering in the cache forever."""
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        recall.recall("ship it", _candidates(), 2)
        cache_path = tmp_path / "skill_embeddings.json"
        assert set(json.loads(cache_path.read_text(encoding="utf-8"))) == {
            "deploy",
            "debug",
            "review",
        }

        # 'review' was uninstalled: a recall over the remaining candidates
        # drops its entry even though nothing needed re-encoding.
        recall2, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        assert recall2.recall("ship it", _candidates()[:2], 2) == ["deploy", "debug"]
        assert set(json.loads(cache_path.read_text(encoding="utf-8"))) == {"deploy", "debug"}


class TestPrefilterIntegration:
    """Test prefilter_ai_triage_candidates with embedding recall wired in."""

    @staticmethod
    def _make_service(embedding_recall: Any = None) -> TriageService:
        config = MagicMock()
        config.ai_triage_circuit_breaker_enabled = True
        config.ai_triage_circuit_breaker_failure_threshold = 3
        config.ai_triage_circuit_breaker_latency_threshold_ms = 500.0
        config.ai_triage_circuit_breaker_cooldown_seconds = 60
        return TriageService(
            config=config,
            cost_tracker=MagicMock(),
            prefilter=MagicMock(),
            cache_manager=MagicMock(),
            get_skill_source=lambda sid, ns: f"{ns}/{sid}",
            embedding_recall=embedding_recall,
        )

    def test_embedding_recall_marks_method(self, tmp_path: Any) -> None:
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        service = self._make_service(embedding_recall=recall)
        result = service.prefilter_ai_triage_candidates("ship it", _candidates(), 2)
        assert [c["id"] for c in result] == ["deploy", "debug"]
        assert service._last_recall_method == "embedding"

    def test_fallback_to_keyword_when_recall_none(self, tmp_path: Any) -> None:
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        recall._model_failed = True
        recall._model = None
        service = self._make_service(embedding_recall=recall)
        result = service.prefilter_ai_triage_candidates("debug", _candidates(), 2)
        assert len(result) == 2
        assert "debug" in {c["id"] for c in result}
        assert service._last_recall_method == "keyword"

    def test_keyword_path_when_no_recall_injected(self) -> None:
        service = self._make_service()
        result = service.prefilter_ai_triage_candidates("debug", _candidates(), 2)
        assert len(result) == 2
        assert service._last_recall_method == "keyword"

    def test_under_limit_skips_recall(self, tmp_path: Any) -> None:
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        service = self._make_service(embedding_recall=recall)
        result = service.prefilter_ai_triage_candidates("ship it", _candidates(), 10)
        assert len(result) == 3
        assert service._last_recall_method is None

    def test_route_metadata_includes_recall_method(self, tmp_path: Any) -> None:
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0])
        service = self._make_service(embedding_recall=recall)
        service._config.enable_ai_triage = True
        service._config.ai_triage_max_skills = 2
        service._config.ai_triage_max_tokens = 500
        service._config.ai_triage_budget_monthly = 5.0
        service._config.ai_triage_log_calls = False
        service._config.ai_triage_timeout_seconds = 15.0
        service._cost_tracker.get_monthly_cost.return_value = 0.0
        service._cache_manager.get.return_value = None
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content='{"skill_id": "deploy", "confidence": 0.9}',
            model="test",
            input_tokens=5,
            output_tokens=5,
        )

        result = service.try_ai_triage("ship it", _candidates())

        assert result is not None
        assert result.match is not None
        assert result.match.metadata["recall_method"] == "embedding"
        assert result.match.metadata["candidates_sent"] == 2

    def test_empty_recall_result_returns_no_candidates(self, tmp_path: Any) -> None:
        """All candidates below the similarity floor: the window is empty
        rather than backfilled with arbitrary (unranked) candidates."""
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0], min_similarity=0.999)
        service = self._make_service(embedding_recall=recall)
        result = service.prefilter_ai_triage_candidates("ship it", _candidates(), 2)
        assert result == []
        assert service._last_recall_method == "embedding"

    def test_partial_clear_backfills_with_below_floor_candidates(self, tmp_path: Any) -> None:
        """When ≥1 but fewer than max_skills candidates clear the floor, the
        window is padded with below-floor candidates in original order — the
        floor only abstains when NOTHING clears it."""
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0], min_similarity=0.5)
        service = self._make_service(embedding_recall=recall)
        result = service.prefilter_ai_triage_candidates("ship it", _candidates(), 2)
        # Only 'deploy' clears 0.5; 'debug' backfills the window.
        assert [c["id"] for c in result] == ["deploy", "debug"]
        assert service._last_recall_method == "embedding"

    def test_try_ai_triage_skips_llm_when_recall_finds_nothing(self, tmp_path: Any) -> None:
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0], min_similarity=0.999)
        service = self._make_service(embedding_recall=recall)
        service._config.enable_ai_triage = True
        service._config.ai_triage_max_skills = 2
        service._config.ai_triage_max_tokens = 500
        service._config.ai_triage_budget_monthly = 5.0
        service._config.ai_triage_log_calls = False
        service._config.ai_triage_timeout_seconds = 15.0
        service._cost_tracker.get_monthly_cost.return_value = 0.0
        service._llm = MagicMock()
        service._llm.configured.return_value = True

        result = service.try_ai_triage("ship it", _candidates())

        assert result is None
        service._llm.call.assert_not_called()


class TestRecallThresholdConfig:
    """RoutingConfig.ai_triage_recall_min_similarity plumbing."""

    @staticmethod
    def _make_service(tmp_path: Any, **config_overrides: Any) -> TriageService:
        config = MagicMock()
        config.ai_triage_circuit_breaker_enabled = True
        config.ai_triage_circuit_breaker_failure_threshold = 3
        config.ai_triage_circuit_breaker_latency_threshold_ms = 500.0
        config.ai_triage_circuit_breaker_cooldown_seconds = 60
        for key, value in config_overrides.items():
            setattr(config, key, value)
        cache_manager = MagicMock()
        cache_manager.cache_dir = tmp_path / "cache"
        return TriageService(
            config=config,
            cost_tracker=MagicMock(),
            prefilter=MagicMock(),
            cache_manager=cache_manager,
            get_skill_source=lambda sid, ns: f"{ns}/{sid}",
        )

    def test_configured_threshold_reaches_recall(self, tmp_path: Any) -> None:
        service = self._make_service(tmp_path, ai_triage_recall_min_similarity=0.5)
        assert service._embedding_recall is not None
        assert service._embedding_recall.min_similarity == 0.5

    def test_missing_threshold_uses_default(self, tmp_path: Any) -> None:
        # MagicMock attribute access returns a MagicMock (not a number) —
        # the service must fall back to the default instead of crashing.
        service = self._make_service(tmp_path)
        assert service._embedding_recall is not None
        assert service._embedding_recall.min_similarity == DEFAULT_MIN_SIMILARITY

    def test_config_swap_after_construction_takes_effect(self, tmp_path: Any) -> None:
        """The floor is re-read from the config per prefilter call, so the
        ``config`` setter swapping in a new RoutingConfig propagates to the
        already-constructed EmbeddingRecall."""
        service = self._make_service(tmp_path, ai_triage_recall_min_similarity=0.5)
        assert service._embedding_recall is not None
        assert service._embedding_recall.min_similarity == 0.5

        new_config = MagicMock()
        new_config.ai_triage_recall_min_similarity = 0.9
        service.config = new_config
        # ≤ max_skills candidates: recall itself is not invoked (no model
        # load), but the floor is still synced at the top of the prefilter.
        service.prefilter_ai_triage_candidates("q", _candidates(), 10)
        assert service._embedding_recall.min_similarity == 0.9

    def test_injected_recall_floor_not_overridden(self, tmp_path: Any) -> None:
        """An injected EmbeddingRecall owns its floor; config sync only
        applies to the recall the service constructed itself."""
        recall, _ = _make_recall(tmp_path, [1.0, 0.0, 0.0], min_similarity=0.7)
        service = TestPrefilterIntegration._make_service(embedding_recall=recall)
        service.prefilter_ai_triage_candidates("ship it", _candidates(), 10)
        assert recall.min_similarity == 0.7
