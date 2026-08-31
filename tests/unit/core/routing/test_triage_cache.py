"""Tests for the persistent cross-process triage cache (.vibe/triage_cache.json)."""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import vibesop.core.routing.triage_cache as triage_cache_module
import vibesop.core.routing.triage_service as triage_service_module
from vibesop.core.models import RoutingLayer
from vibesop.core.routing.triage_cache import TriageCache
from vibesop.core.routing.triage_service import TriageService
from vibesop.utils.file_lock import cross_process_lock

_CANDIDATES = [{"id": "skill-a", "intent": "test"}, {"id": "skill-b", "intent": "test2"}]
_ROUTE = {
    "skill_id": "skill-a",
    "confidence": 0.88,
    "layer": "ai_triage",
    "source": "builtin/skill-a",
    "description": "test",
    "metadata": {},
}


def _store(cache: TriageCache, query: str = "hello world", **overrides: Any) -> None:
    route = {**_ROUTE, **overrides}
    cache.store(query, _CANDIDATES, route)


class TestLookup:
    """Fresh / stale / miss semantics of TriageCache.lookup."""

    def test_fresh_hit(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        _store(cache)
        fresh, stale = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is not None
        assert fresh["skill_id"] == "skill-a"
        assert stale is None

    def test_normalization_matches(self, tmp_path) -> None:
        """Whitespace/case variants of the same query hit the same entry."""
        cache = TriageCache(tmp_path)
        _store(cache, query="Hello   World")
        fresh, _ = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is not None

    def test_miss_returns_none(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        fresh, stale = cache.lookup("nope", _CANDIDATES, ttl_hours=72)
        assert fresh is None
        assert stale is None

    def test_ttl_expired_is_stale(self, tmp_path) -> None:
        """Expired entry is a miss but kept as last-good."""
        cache = TriageCache(tmp_path)
        _store(cache)
        # Backdate the entry beyond the TTL.
        data = json.loads(cache.cache_path.read_text(encoding="utf-8"))
        key = TriageCache.key_for("hello world")
        data[key]["ts"] = time.time() - 100 * 3600
        cache.cache_path.write_text(json.dumps(data), encoding="utf-8")

        fresh, stale = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is None
        assert stale is not None
        assert stale["skill_id"] == "skill-a"

    def test_candidates_hash_mismatch_is_stale(self, tmp_path) -> None:
        """Changed skill set is a miss but kept as last-good."""
        cache = TriageCache(tmp_path)
        _store(cache)
        changed = [*_CANDIDATES, {"id": "skill-c", "intent": "new"}]
        fresh, stale = cache.lookup("hello world", changed, ttl_hours=72)
        assert fresh is None
        assert stale is not None

    def test_corrupt_file_self_heals(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        cache.cache_path.write_text("{not valid json", encoding="utf-8")
        fresh, stale = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is None
        assert stale is None
        # Next store overwrites the corrupt state.
        _store(cache)
        fresh, _ = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is not None

    def test_lock_contention_degrades_to_miss(self, tmp_path) -> None:
        """A held lock must not stall routing: lookup/store silently no-op."""
        cache = TriageCache(tmp_path)
        _store(cache)
        with cross_process_lock(cache.lock_path, blocking=False):
            fresh, stale = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
            assert fresh is None
            assert stale is None
            _store(cache, query="blocked write")  # silently dropped
        # Lock released: previous entry intact, blocked write absent.
        fresh, _ = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is not None
        fresh, _ = cache.lookup("blocked write", _CANDIDATES, ttl_hours=72)
        assert fresh is None


class TestCapacity:
    """Oldest entries are evicted past MAX_ENTRIES."""

    def test_evicts_oldest_by_ts(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(triage_cache_module, "MAX_ENTRIES", 3)
        cache = TriageCache(tmp_path)
        for i in range(5):
            _store(cache, query=f"query {i}")
            time.sleep(0.01)  # ensure distinct timestamps

        data = json.loads(cache.cache_path.read_text(encoding="utf-8"))
        assert len(data) == 3
        assert TriageCache.key_for("query 0") not in data
        assert TriageCache.key_for("query 1") not in data
        for i in (2, 3, 4):
            assert TriageCache.key_for(f"query {i}") in data


class TestTmpCleanup:
    """A crashed writer leaks ``triage_cache.<pid>.tmp`` forever — reads
    sweep the leftovers (the tmp is renamed atomically on success, so any
    survivor means the writer died)."""

    def test_stale_pid_tmp_removed_on_read(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        _store(cache)
        stale = tmp_path / "triage_cache.999999.tmp"
        stale.write_text('{"partial": true', encoding="utf-8")

        cache.lookup("hello world", _CANDIDATES, ttl_hours=72)

        assert not stale.exists()
        # The real cache file is untouched by the sweep.
        fresh, _ = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is not None

    def test_unrelated_tmp_files_survive(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        _store(cache)
        unrelated = tmp_path / "other_tool.123.tmp"
        unrelated.write_text("keep me", encoding="utf-8")

        cache.lookup("hello world", _CANDIDATES, ttl_hours=72)

        assert unrelated.exists()


class TestPrivacy:
    """No raw query text is persisted."""

    def test_cache_file_has_no_query_text(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        secret_query = "deploy the frobnicate service now"
        _store(cache, query=secret_query)
        content = cache.cache_path.read_text(encoding="utf-8")
        assert secret_query not in content
        assert "frobnicate" not in content


def _make_service(
    triage_cache: TriageCache,
    timeout_seconds: float = 15.0,
) -> TriageService:
    """TriageService with mocked deps and a real persistent cache."""
    config = MagicMock()
    config.enable_ai_triage = True
    config.ai_triage_budget_monthly = 5.0
    config.ai_triage_log_calls = False
    config.ai_triage_max_skills = 10
    config.ai_triage_max_tokens = 500
    config.ai_triage_prompt_version = "v2"
    config.ai_triage_circuit_breaker_enabled = True
    config.ai_triage_circuit_breaker_failure_threshold = 3
    config.ai_triage_circuit_breaker_latency_threshold_ms = 500.0
    config.ai_triage_circuit_breaker_cooldown_seconds = 60
    config.ai_triage_timeout_seconds = timeout_seconds
    config.triage_cache_ttl_hours = 72

    cost_tracker = MagicMock()
    cost_tracker.get_monthly_cost.return_value = 0.0
    cache_manager = MagicMock()  # only used to locate .vibe; mocked dir -> None

    service = TriageService(
        config=config,
        cost_tracker=cost_tracker,
        prefilter=MagicMock(),
        cache_manager=cache_manager,
        get_skill_source=lambda sid, ns: f"{ns}/{sid}",
        triage_cache=triage_cache,
    )
    service._llm = MagicMock()
    service._llm.configured.return_value = True
    return service


class TestServiceIntegration:
    """Persistent cache wired into TriageService.try_ai_triage."""

    def test_fresh_hit_skips_llm(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        _store(cache)
        service = _make_service(cache)

        result = service.try_ai_triage("hello world", _CANDIDATES)
        assert result is not None
        assert result.layer == RoutingLayer.AI_TRIAGE
        assert result.match.skill_id == "skill-a"
        assert result.match.metadata["persistent_cache"] is True
        service._llm.call.assert_not_called()

    def test_fresh_hit_bypasses_open_circuit(self, tmp_path) -> None:
        """Fresh persistent hits cost nothing, so an open breaker must not
        block them (the breaker only guards the LLM call path)."""
        cache = TriageCache(tmp_path)
        _store(cache)
        service = _make_service(cache)
        service._circuit_breaker.trip("manual")

        result = service.try_ai_triage("hello world", _CANDIDATES)
        assert result is not None
        assert result.match.skill_id == "skill-a"
        assert result.match.metadata["persistent_cache"] is True
        service._llm.call.assert_not_called()

    def test_fresh_hit_bypasses_exhausted_budget(self, tmp_path) -> None:
        """Fresh persistent hits survive an exhausted monthly budget; the
        budget gate never runs, so it must not trip the breaker either."""
        cache = TriageCache(tmp_path)
        _store(cache)
        service = _make_service(cache)
        service._cost_tracker.get_monthly_cost.return_value = 99.0

        result = service.try_ai_triage("hello world", _CANDIDATES)
        assert result is not None
        assert result.match.skill_id == "skill-a"
        assert result.match.metadata["persistent_cache"] is True
        service._llm.call.assert_not_called()
        assert service._circuit_breaker.state != "open"

    def test_successful_call_stores_entry(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        service = _make_service(cache)
        service._llm.call.return_value = MagicMock(
            content='{"skill_id": "skill-a"}', model="test", input_tokens=5, output_tokens=5
        )

        result = service.try_ai_triage("hello world", _CANDIDATES)
        assert result is not None
        fresh, _ = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is not None
        assert fresh["skill_id"] == "skill-a"

    def test_last_good_on_llm_failure(self, tmp_path) -> None:
        """LLM failure + stale entry (changed candidates) -> last-good route."""
        cache = TriageCache(tmp_path)
        _store(cache)  # stored against _CANDIDATES
        service = _make_service(cache)
        service._llm.call.side_effect = RuntimeError("LLM down")

        # Skill set changed -> entry is stale, but skill-a still exists.
        changed = [*_CANDIDATES, {"id": "skill-c", "intent": "new"}]
        result = service.try_ai_triage("hello world", changed)
        assert result is not None
        assert result.match.skill_id == "skill-a"
        assert result.match.metadata["last_good"] is True

    def test_last_good_confidence_is_decayed(self, tmp_path) -> None:
        """Stale confidence is decayed x0.7; the original value is recorded."""
        cache = TriageCache(tmp_path)
        _store(cache, confidence=0.82)
        service = _make_service(cache)
        service._llm.call.side_effect = RuntimeError("LLM down")

        changed = [*_CANDIDATES, {"id": "skill-c", "intent": "new"}]
        result = service.try_ai_triage("hello world", changed)
        assert result is not None
        assert result.match.confidence == pytest.approx(0.82 * 0.7)
        assert result.match.metadata["last_good_original_confidence"] == pytest.approx(0.82)

    def test_last_good_decay_may_fall_below_min_confidence(self, tmp_path) -> None:
        """A stale 0.82 decays to ~0.574, below the router's default
        min_confidence (0.6) — intentional: stale results must not
        auto-execute downstream (unified.py rejects them)."""
        cache = TriageCache(tmp_path)
        _store(cache, confidence=0.82)
        service = _make_service(cache)
        service._llm.call.side_effect = RuntimeError("LLM down")

        changed = [*_CANDIDATES, {"id": "skill-c", "intent": "new"}]
        result = service.try_ai_triage("hello world", changed)
        assert result is not None
        assert result.match.confidence < 0.6
        assert result.match.metadata["last_good"] is True

    def test_last_good_reachable_when_circuit_open(self, tmp_path) -> None:
        """Open breaker + stale entry -> last-good route instead of None.
        The circuit gate runs before the prefilter, so the recall cost is
        never paid, and the last-good route reports candidates_sent=0 (no
        prompt was ever sent to the LLM)."""
        cache = TriageCache(tmp_path)
        _store(cache)
        service = _make_service(cache)
        service._circuit_breaker.trip("manual")

        changed = [*_CANDIDATES, {"id": "skill-c", "intent": "new"}]
        with patch.object(
            service,
            "prefilter_ai_triage_candidates",
            wraps=service.prefilter_ai_triage_candidates,
        ) as mock_prefilter:
            result = service.try_ai_triage("hello world", changed)
        assert result is not None
        assert result.match.skill_id == "skill-a"
        assert result.match.metadata["last_good"] is True
        assert result.match.metadata["candidates_sent"] == 0
        mock_prefilter.assert_not_called()
        service._llm.call.assert_not_called()

    def test_last_good_reachable_when_budget_exhausted(self, tmp_path) -> None:
        """Exhausted budget + stale entry -> last-good route (breaker still
        trips, preserving the budget-enforcement side effect). The budget
        gate runs before the prefilter, so the recall cost is never paid."""
        cache = TriageCache(tmp_path)
        _store(cache)
        service = _make_service(cache)
        service._cost_tracker.get_monthly_cost.return_value = 99.0

        changed = [*_CANDIDATES, {"id": "skill-c", "intent": "new"}]
        with patch.object(
            service,
            "prefilter_ai_triage_candidates",
            wraps=service.prefilter_ai_triage_candidates,
        ) as mock_prefilter:
            result = service.try_ai_triage("hello world", changed)
        assert result is not None
        assert result.match.skill_id == "skill-a"
        assert result.match.metadata["last_good"] is True
        assert result.match.metadata["candidates_sent"] == 0
        mock_prefilter.assert_not_called()
        service._llm.call.assert_not_called()
        assert service._circuit_breaker.state == "open"

    def test_circuit_open_without_stale_entry_returns_none(self, tmp_path) -> None:
        """Open breaker without any stale entry still returns None."""
        cache = TriageCache(tmp_path)
        service = _make_service(cache)
        service._circuit_breaker.trip("manual")

        result = service.try_ai_triage("hello world", _CANDIDATES)
        assert result is None
        service._llm.call.assert_not_called()

    def test_last_good_rejected_when_skill_removed(self, tmp_path) -> None:
        """A stale entry whose skill left the candidate set is not used."""
        cache = TriageCache(tmp_path)
        _store(cache)  # entry for skill-a
        service = _make_service(cache)
        service._llm.call.side_effect = RuntimeError("LLM down")

        result = service.try_ai_triage("hello world", [{"id": "skill-b", "intent": "t"}])
        assert result is None

    def test_llm_timeout_falls_through(self, tmp_path) -> None:
        """Slow LLM exceeding ai_triage_timeout_seconds is treated as failure."""
        service = _make_service(TriageCache(tmp_path), timeout_seconds=0.05)

        def _slow_call(**_kwargs: Any) -> None:
            time.sleep(0.5)
            raise AssertionError("should have timed out before completing")

        service._llm.call.side_effect = _slow_call
        result = service.try_ai_triage("hello world", _CANDIDATES)
        assert result is None
        assert service._circuit_breaker._consecutive_failures == 1

    def test_fresh_hit_skips_prefilter(self, tmp_path) -> None:
        """Lookup runs before the prefilter: a fresh hit returns without ever
        paying the (potentially expensive) embedding/keyword recall cost."""
        cache = TriageCache(tmp_path)
        _store(cache)
        service = _make_service(cache)
        service._embedding_recall = MagicMock()

        with patch.object(
            service,
            "prefilter_ai_triage_candidates",
            wraps=service.prefilter_ai_triage_candidates,
        ) as mock_prefilter:
            result = service.try_ai_triage("hello world", _CANDIDATES)

        assert result is not None
        assert result.match.skill_id == "skill-a"
        assert result.match.metadata["persistent_cache"] is True
        mock_prefilter.assert_not_called()
        service._embedding_recall.recall.assert_not_called()
        service._llm.call.assert_not_called()

    def test_store_uses_full_candidate_set_hash(self, tmp_path) -> None:
        """The persisted candidates_hash covers the full candidate list, not
        the prefiltered top-N window — that is what lets the lookup run
        before prefiltering."""
        cache = TriageCache(tmp_path)
        service = _make_service(cache)  # ai_triage_max_skills = 10
        service._llm.call.return_value = MagicMock(
            content='{"skill_id": "skill-a"}', model="test", input_tokens=5, output_tokens=5
        )
        # 12 candidates -> the prefilter window (10) is smaller than the set;
        # pin the window deterministically via a mocked recall.
        service._embedding_recall = MagicMock()
        service._embedding_recall.recall.return_value = ["skill-a"] + [
            f"filler-{i}" for i in range(9)
        ]
        many = [{"id": "skill-a", "intent": "test"}] + [
            {"id": f"filler-{i}", "intent": f"unrelated {i}"} for i in range(11)
        ]

        result = service.try_ai_triage("hello world", many)
        assert result is not None

        data = json.loads(cache.cache_path.read_text(encoding="utf-8"))
        entry = data[TriageCache.key_for("hello world")]
        assert entry["candidates_hash"] == TriageCache.candidates_hash(many)
        # A lookup with the same full set is fresh...
        fresh, _ = cache.lookup("hello world", many, ttl_hours=72)
        assert fresh is not None
        # ...and dropping a skill that never reached the LLM window still
        # demotes the entry to stale.
        reduced = [c for c in many if c["id"] != "filler-10"]
        fresh, stale = cache.lookup("hello world", reduced, ttl_hours=72)
        assert fresh is None
        assert stale is not None

    def test_last_good_validates_against_full_candidate_set(self, tmp_path) -> None:
        """Last-good aliveness is checked against the full candidate set: a
        stale skill that fell outside the prefiltered top-N window is still
        usable, because it is still installed."""
        cache = TriageCache(tmp_path)
        _store(cache)  # entry for skill-a, hashed over _CANDIDATES
        service = _make_service(cache)  # ai_triage_max_skills = 10
        service._llm.call.side_effect = RuntimeError("LLM down")
        # The recall window excludes skill-a entirely.
        service._embedding_recall = MagicMock()
        service._embedding_recall.recall.return_value = [f"filler-{i}" for i in range(10)]

        # skill-a is installed but ranked outside the top-10 window, and the
        # set changed (hash mismatch -> the entry is stale).
        many = [{"id": "skill-a", "intent": "test"}] + [
            {"id": f"filler-{i}", "intent": f"unrelated {i}"} for i in range(11)
        ]
        result = service.try_ai_triage("hello world", many)

        assert result is not None
        assert result.match.skill_id == "skill-a"
        assert result.match.metadata["last_good"] is True
        # The prefilter really did run and really did exclude skill-a.
        assert service._last_recall_method == "embedding"

    def test_last_good_decay_constant(self) -> None:
        """The last-good decay factor is a named module constant, value 0.7."""
        assert triage_service_module.LAST_GOOD_CONFIDENCE_DECAY == 0.7


class TestUnstructuredReplies:
    """Routing-precision audit 2026-08-29: unstructured triage replies must
    not inject a route nor poison the persistent cache."""

    def test_bare_token_reply_no_result_negative_store(self, tmp_path) -> None:
        """Round-2: the drop itself is cached as a no-match so the repeat
        query skips the LLM (hook traffic is negative-dominated)."""
        cache = TriageCache(tmp_path)
        service = _make_service(cache)
        service._llm.call.return_value = MagicMock(
            content="skill-a", model="test", input_tokens=5, output_tokens=5
        )

        result = service.try_ai_triage("hello world", _CANDIDATES)
        assert result is None
        fresh, _ = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is not None
        assert fresh["skill_id"] is None

    def test_structured_reply_still_stores(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        service = _make_service(cache)
        service._llm.call.return_value = MagicMock(
            content='{"skill_id": "skill-a", "confidence": 0.93}',
            model="test",
            input_tokens=5,
            output_tokens=5,
        )

        result = service.try_ai_triage("hello world", _CANDIDATES)
        assert result is not None
        assert result.match.confidence == pytest.approx(0.93)
        fresh, _ = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is not None


class TestSchemaVersionGate:
    """Entries written before the 2026-08-29 unstructured-reply fix may
    encode forced-match false positives; they must not survive as fresh
    hits or last-good fallbacks."""

    def _write_legacy_entry(self, cache: TriageCache, query: str = "hello world") -> None:
        key = TriageCache.key_for(query)
        data = {
            key: {
                "skill_id": "skill-a",
                "confidence": 0.82,
                "source": "builtin/skill-a",
                "description": "",
                "candidates_hash": TriageCache.candidates_hash(_CANDIDATES),
                "ts": time.time(),
            }
        }
        cache.cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache.cache_path.write_text(json.dumps(data), encoding="utf-8")

    def test_legacy_entry_without_version_is_ignored(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        self._write_legacy_entry(cache)
        fresh, stale = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is None
        assert stale is None

    def test_wrong_version_is_ignored(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        _store(cache)
        data = json.loads(cache.cache_path.read_text(encoding="utf-8"))
        data[TriageCache.key_for("hello world")]["v"] = 99
        cache.cache_path.write_text(json.dumps(data), encoding="utf-8")

        fresh, stale = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is None
        assert stale is None

    def test_stored_entry_carries_version(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        _store(cache)
        data = json.loads(cache.cache_path.read_text(encoding="utf-8"))
        entry = data[TriageCache.key_for("hello world")]
        assert entry["v"] == TriageCache.SCHEMA_VERSION


class TestNegativeCaching:
    """Round-2 review: repeat negative queries must not re-pay the LLM call
    (hook traffic is negative-dominated; pre-fix only (wrong) matches were
    cached)."""

    def _store_negative(self, cache: TriageCache, query: str = "hello world") -> None:
        cache.store(
            query,
            _CANDIDATES,
            {"skill_id": None, "confidence": 0.0, "source": "", "description": ""},
        )

    def test_negative_fresh_within_short_ttl(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        self._store_negative(cache)
        fresh, stale = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is not None
        assert fresh["skill_id"] is None
        assert stale is None

    def test_negative_expires_at_6h_even_under_72h_ttl(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        self._store_negative(cache)
        data = json.loads(cache.cache_path.read_text(encoding="utf-8"))
        data[TriageCache.key_for("hello world")]["ts"] = time.time() - 7 * 3600
        cache.cache_path.write_text(json.dumps(data), encoding="utf-8")

        fresh, stale = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is None
        # Expired negatives still surface in the stale slot, but the service
        # never resurrects a no-match as a last-good route.
        assert stale is not None
        assert stale["skill_id"] is None
        service = _make_service(cache)
        assert service._last_good_route(stale, _CANDIDATES) is None

    def test_structured_none_reply_negative_hit_skips_llm(self, tmp_path) -> None:
        """A cached no-match short-circuits before the LLM call."""
        cache = TriageCache(tmp_path)
        service = _make_service(cache)
        service._llm.call.return_value = MagicMock(
            content='{"skill_id": null}', model="test", input_tokens=5, output_tokens=5
        )
        assert service.try_ai_triage("hello world", _CANDIDATES) is None  # stores negative

        service2 = _make_service(cache)
        service2._llm.call.side_effect = AssertionError("must not call LLM on negative hit")
        assert service2.try_ai_triage("hello world", _CANDIDATES) is None

    def test_unstructured_drop_also_caches_negative(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        service = _make_service(cache)
        service._llm.call.return_value = MagicMock(
            content="skill-a", model="test", input_tokens=5, output_tokens=5
        )
        assert service.try_ai_triage("hello world", _CANDIDATES) is None
        fresh, _ = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is not None
        assert fresh["skill_id"] is None

    def test_version_mismatch_evicts_legacy_entry(self, tmp_path) -> None:
        """Lookup self-heals: incompatible entries are removed, not left to
        squat in the file forever."""
        cache = TriageCache(tmp_path)
        key = TriageCache.key_for("hello world")
        data = {
            key: {
                "skill_id": "skill-a",
                "confidence": 0.82,
                "candidates_hash": TriageCache.candidates_hash(_CANDIDATES),
                "ts": time.time(),
            }
        }
        cache.cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache.cache_path.write_text(json.dumps(data), encoding="utf-8")

        fresh, stale = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is None
        assert stale is None
        after = json.loads(cache.cache_path.read_text(encoding="utf-8"))
        assert key not in after

    def test_locked_reread_does_not_evict_concurrent_upgrade(self, tmp_path, monkeypatch) -> None:
        """Between the unlocked read and the locked re-read a concurrent
        store may upgrade the entry to the current schema version — the
        eviction must re-check the version under the lock instead of
        popping unconditionally."""
        cache = TriageCache(tmp_path)
        key = TriageCache.key_for("hello world")
        legacy = {key: {"skill_id": "skill-a", "ts": time.time()}}  # no "v"
        cache.cache_path.write_text(json.dumps(legacy), encoding="utf-8")

        upgraded = {
            key: {
                "v": TriageCache.SCHEMA_VERSION,
                "skill_id": "skill-a",
                "confidence": 0.9,
                "candidates_hash": TriageCache.candidates_hash(_CANDIDATES),
                "ts": time.time(),
            }
        }
        real_read = cache._read
        reads = 0

        def concurrent_store_then_read() -> dict:
            nonlocal reads
            reads += 1
            if reads == 2:
                # The locked re-read: a concurrent store has landed since
                # the unlocked read above.
                cache.cache_path.write_text(json.dumps(upgraded), encoding="utf-8")
            return real_read()

        monkeypatch.setattr(cache, "_read", concurrent_store_then_read)

        fresh, stale = cache.lookup("hello world", _CANDIDATES, ttl_hours=72)
        assert fresh is None
        assert stale is None
        after = json.loads(cache.cache_path.read_text(encoding="utf-8"))
        assert key in after
        assert after[key]["v"] == TriageCache.SCHEMA_VERSION

    def test_negative_entry_never_resurrects_as_last_good(self, tmp_path) -> None:
        cache = TriageCache(tmp_path)
        self._store_negative(cache)
        # Make it stale (skill set changed).
        changed = [*_CANDIDATES, {"id": "skill-c", "intent": "new"}]
        service = _make_service(cache)
        service._llm.call.side_effect = RuntimeError("LLM down")

        result = service.try_ai_triage("hello world", changed)
        assert result is None
