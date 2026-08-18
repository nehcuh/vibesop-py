# 门禁5 复审包:M5(nits 全量收敛)

## M5 变更
M5a(triage_service.py):fresh 命中补 session-end 守卫防御性复用 + metadata 补 model=cache/structured 键;预算耗尽单条日志(成本并入 trip reason);import time 上移+超时成本注释;_resolve_vibe_dir 锚定两种 cache_dir 形态。
M5b(unified.py, orchestrator.py):junk 判据改 _is_junk_query(lstrip 后前缀匹配,防字面讨论误杀);orchestrate 路径 junk no-match 短路,不进 decompose;判据单一来源 lazy import 复用。
M5c(test_index_layer.py, .gitignore, agent_runtime.py, build_eval_from_logs.py):预存失败测试改 patch.dict sys.modules None 正确模拟未安装;.gitignore 加 5 条运行时文件规则并删除残留;agent_runtime 同步 api_key 空 warning;merge 主集缺 query 跳过+警告。
M5d(_layers.py 未改/analytics.py/manager.py 未改):bigram 阈值标定(结论:保持 0.20,低置信,artifact 在 .omx/artifacts/bigram-threshold-calibration.md);AnalyticsStore LastRouteTracker 单实例+内存缓存,稳态省一次文件读(跨进程信号退化为本进程上一次,已测试钉死);附带发现 index_match_threshold 不在 RoutingConfig 中(getattr 兜底)。

注意:diff 相对 HEAD 含 M1-M4 已审内容,聚焦 M5 增量。

## diff
diff --git a/.gitignore b/.gitignore
index f9f628d..114a116 100644
--- a/.gitignore
+++ b/.gitignore
@@ -83,6 +83,12 @@ htmlcov/
 .vibe/routing_counter.json
 .vibe/miss_counter.json
 .vibe/miss_salt
+# Routing runtime caches/state (triage cache, last route, skill embeddings)
+.vibe/triage_cache.json
+.vibe/triage_cache.lock
+.vibe/last_route.json
+.vibe/skill_embeddings.json
+.vibe/skill_embeddings.lock
 .vibe/*.bak*
 .vibe/*.backup
 .vibe/*-report.md
diff --git a/src/vibesop/agent/runtime/agent_runtime.py b/src/vibesop/agent/runtime/agent_runtime.py
index 307ece9..c5ed95e 100644
--- a/src/vibesop/agent/runtime/agent_runtime.py
+++ b/src/vibesop/agent/runtime/agent_runtime.py
@@ -323,6 +323,18 @@ class AgentRuntime:
             cfg = resolver.get_llm_for_understanding()
             if not cfg or not cfg.provider:
                 return None
+            if not cfg.api_key:
+                # Same warning as cli/main.py:_build_llm_factory() — an
+                # empty api_key means the configured provider/api_base fall
+                # back to environment variable detection.
+                logger.warning(
+                    "Config [llm] found but api_key is empty; configured "
+                    "provider/api_base (%s/%s) are ignored, falling back to "
+                    "environment variable detection. Set api_key in the config "
+                    "or export the provider's API key env var.",
+                    cfg.provider,
+                    cfg.api_base,
+                )
 
             def _factory():
                 return create_provider(
diff --git a/src/vibesop/core/analytics.py b/src/vibesop/core/analytics.py
index 6c14c7c..2667171 100644
--- a/src/vibesop/core/analytics.py
+++ b/src/vibesop/core/analytics.py
@@ -6,6 +6,7 @@ to enable continuous improvement of the routing system.
 
 from __future__ import annotations
 
+import hashlib
 import json
 import logging
 from dataclasses import dataclass, field
@@ -17,6 +18,10 @@ from vibesop.utils.redaction import redact_sensitive
 
 logger = logging.getLogger(__name__)
 
+_RAPID_REROUTE_SECONDS = 10.0
+_OVERLAP_THRESHOLD = 0.5
+_HASH_LENGTH = 16
+
 
 @dataclass
 class ExecutionRecord:
@@ -66,6 +71,120 @@ class ExecutionRecord:
         )
 
 
+class LastRouteTracker:
+    """Tracks the previous route per project to derive implicit feedback signals.
+
+    Persists ``.vibe/last_route.json`` (token hashes + skill + timestamp — no
+    raw query text). Read-modify-write is serialised via a sibling ``.lock``
+    file (same pattern as ``.vibe/instincts.jsonl.lock``). The state this
+    process last wrote is cached in memory, so the steady-state critical
+    section skips the file read entirely; cross-process interleavings degrade
+    to per-process signals (best-effort telemetry, last writer wins).
+
+    Fails open: corrupt state, lock contention, or any IO error yields no
+    implicit signals and never breaks the routing/analytics main flow.
+    """
+
+    def __init__(self, storage_dir: str | Path = ".vibe") -> None:
+        self.state_path = Path(storage_dir) / "last_route.json"
+        self.lock_path = Path(storage_dir) / "last_route.lock"
+        # In-memory copy of the state this process last wrote. While held,
+        # the file read inside the lock is skipped (steady-state hot path
+        # drops from stat+open+read+parse to zero reads). Cross-process
+        # staleness is accepted: implicit signals are best-effort telemetry
+        # about *this* session's re-routes, and a concurrent writer's state
+        # being overwritten by our next write matches "last route wins".
+        self._cached_state: dict[str, Any] | None = None
+
+    def compute_and_update(
+        self,
+        query: str,
+        skill: str | None,
+        now: datetime | None = None,
+    ) -> dict[str, Any]:
+        """Compute implicit signals vs. the last route, then record this one.
+
+        Returns the signal fields to merge into the analytics event; empty
+        dict on first route or any failure (silent degradation).
+        """
+        try:
+            from vibesop.utils.file_lock import cross_process_lock
+
+            now = now or datetime.now(UTC)
+            normalized = " ".join(redact_sensitive(query).split()).lower()
+            token_hashes = sorted(
+                {_hash_token(t) for t in normalized.split() if t}
+            )
+            # Non-blocking: a contended lock must never stall routing (M1d);
+            # the critical section is a tiny RMW so contention is rare.
+            with cross_process_lock(self.lock_path, blocking=False):
+                last = self._cached_state if self._cached_state is not None else self._read()
+                signals = _implicit_signals(last, token_hashes, now)
+                state = {
+                    "token_hashes": token_hashes,
+                    "skill": skill,
+                    "timestamp": now.isoformat(),
+                }
+                self._write(state)
+                # Cache only after a successful write, so a failed _write
+                # (exception → silent degradation) never poisons the cache.
+                self._cached_state = state
+            return signals
+        except Exception as e:  # telemetry must never break routing
+            logger.debug("Implicit feedback signals unavailable: %s", e)
+            return {}
+
+    def _read(self) -> dict[str, Any] | None:
+        """Read last-route state; corrupt/missing state returns None (self-heals
+        on the next ``_write``). Single open — no ``exists()`` pre-check."""
+        try:
+            with self.state_path.open("r", encoding="utf-8") as f:
+                data = json.load(f)
+        except (json.JSONDecodeError, OSError):
+            return None
+        return data if isinstance(data, dict) else None
+
+    def _write(self, state: dict[str, Any]) -> None:
+        self.state_path.parent.mkdir(parents=True, exist_ok=True)
+        with self.state_path.open("w", encoding="utf-8") as f:
+            json.dump(state, f, ensure_ascii=False)
+
+
+def _hash_token(token: str) -> str:
+    """Per-token hash so Jaccard overlap can be computed without storing raw
+    query text (hashed-set equality matches raw-set equality)."""
+    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
+
+
+def _implicit_signals(
+    last: dict[str, Any] | None,
+    token_hashes: list[str],
+    now: datetime,
+) -> dict[str, Any]:
+    """Derive implicit quality signals from the previous route state."""
+    if not last:
+        return {}
+
+    signals: dict[str, Any] = {}
+    try:
+        last_ts = datetime.fromisoformat(str(last["timestamp"]))
+        # Clamp clock skew (e.g. NTP rollback) to 0 instead of reporting
+        # negative seconds.
+        seconds = max(0.0, (now - last_ts).total_seconds())
+        signals["seconds_since_last_route"] = round(seconds, 3)
+        signals["is_rapid_reroute"] = seconds < _RAPID_REROUTE_SECONDS
+    except (KeyError, TypeError, ValueError):
+        pass
+
+    last_tokens = set(last.get("token_hashes") or [])
+    if last_tokens and token_hashes:
+        union = last_tokens | set(token_hashes)
+        jaccard = len(last_tokens & set(token_hashes)) / len(union)
+        signals["query_overlap_with_last"] = jaccard > _OVERLAP_THRESHOLD
+
+    return signals
+
+
 class AnalyticsStore:
     """Persistent store for execution analytics.
 
@@ -75,12 +194,31 @@ class AnalyticsStore:
     def __init__(self, storage_dir: str | Path = ".vibe") -> None:
         self.storage_path = Path(storage_dir) / "analytics.jsonl"
         self.storage_path.parent.mkdir(parents=True, exist_ok=True)
+        # One tracker per store: previously constructed per record(), which
+        # also defeated its in-memory state cache (see LastRouteTracker).
+        self._last_route = LastRouteTracker(self.storage_path.parent)
 
     def record(self, record: ExecutionRecord) -> None:
-        """Append an execution record (query redacted — F-06)."""
+        """Append an execution record (query redacted — F-06).
+
+        Also merges implicit feedback signals (seconds since last route,
+        rapid re-route, query overlap) derived from ``.vibe/last_route.json``
+        — additive fields only, absent when unavailable (M1d).
+
+        Hot-path IO: the analytics write itself is a bare O(1) append (no
+        lock, no read). The implicit-signal update adds one non-blocking
+        lock + one small JSON write; the state read is served from the
+        tracker's in-memory cache in steady state, so a record costs one
+        lock + two writes total instead of lock + read + two writes.
+        """
         try:
             data = record.to_dict()
             data["query"] = redact_sensitive(data["query"])
+            data.update(
+                self._last_route.compute_and_update(
+                    record.query, record.primary_skill
+                )
+            )
             with self.storage_path.open("a", encoding="utf-8") as f:
                 f.write(json.dumps(data, ensure_ascii=False) + "\n")
         except OSError as e:
diff --git a/src/vibesop/core/routing/orchestrator.py b/src/vibesop/core/routing/orchestrator.py
index c46b6aa..8bb0bc0 100644
--- a/src/vibesop/core/routing/orchestrator.py
+++ b/src/vibesop/core/routing/orchestrator.py
@@ -185,6 +185,17 @@ class Orchestrator:
         if not self._router._config.enable_orchestration:
             return self._router._to_orchestration_result(single_result, query)
 
+        # Junk short-circuit: _single_skill_route already returned a no-match
+        # for harness-markup queries, but the detector's primary=None branch
+        # treats any long no-match query as a possible multi-part request and
+        # would decompose the garbage text. Reuse unified.py's predicate (lazy
+        # import — unified imports Orchestrator at module load) rather than a
+        # third copy of the criterion.
+        from vibesop.core.routing.unified import _is_junk_query
+
+        if _is_junk_query(query):
+            return self._router._to_orchestration_result(single_result, query)
+
         # 3. Multi-intent detection
         with self._phase_span("detection", query):
             cb.on_phase_start(
diff --git a/src/vibesop/core/routing/triage_service.py b/src/vibesop/core/routing/triage_service.py
index 8a2a8d5..ec90f7a 100644
--- a/src/vibesop/core/routing/triage_service.py
+++ b/src/vibesop/core/routing/triage_service.py
@@ -4,6 +4,9 @@ from __future__ import annotations
 
 import logging
 import os
+import threading
+import time
+from pathlib import Path
 from typing import TYPE_CHECKING, Any
 
 from vibesop.core.matching import KeywordMatcher, MatcherConfig
@@ -11,6 +14,8 @@ from vibesop.core.models import RoutingLayer, SkillRoute
 from vibesop.core.routing._protocols import LLMFactory, PromptBuilder
 from vibesop.core.routing.circuit_breaker import TriageCircuitBreaker
 from vibesop.core.routing.layers import LayerResult
+from vibesop.core.routing.triage_cache import TriageCache
+from vibesop.core.routing.triage_recall import EmbeddingRecall
 
 if TYPE_CHECKING:
     from collections.abc import Callable
@@ -22,6 +27,21 @@ if TYPE_CHECKING:
 
 logger = logging.getLogger(__name__)
 
+# Decay applied to a stale (last-good) cached confidence so it never competes
+# with a fresh LLM result at full weight.
+LAST_GOOD_CONFIDENCE_DECAY = 0.7
+
+
+def _resolve_vibe_dir(cache_dir: str | Path) -> Path:
+    """Locate the .vibe dir from a cache dir.
+
+    Standard layout is ``<root>/.vibe/cache``, where the .vibe dir is the
+    parent. When cache_dir is already the .vibe dir itself (custom setups),
+    use it as-is instead of blindly walking up one level.
+    """
+    path = Path(cache_dir)
+    return path.parent if path.name == "cache" else path
+
 
 class TriageService:
     """AI Triage layer for skill routing."""
@@ -35,15 +55,46 @@ class TriageService:
         get_skill_source: Callable[..., str],
         llm_factory: LLMFactory | None = None,
         prompt_builder: PromptBuilder | None = None,
+        triage_cache: TriageCache | None = None,
+        embedding_recall: EmbeddingRecall | None = None,
     ) -> None:
         self._config = config
         self._cost_tracker = cost_tracker
         self._prefilter = prefilter
+        # Retained for backward compatibility and to locate the .vibe dir
+        # below; triage results are no longer cached via CacheManager (the
+        # persistent TriageCache is the single triage cache).
         self._cache_manager = cache_manager
         self._get_skill_source = get_skill_source
         self._llm_factory = llm_factory
         self._prompt_builder = prompt_builder
         self._llm: Any | None = None
+        # Persistent cross-process cache (.vibe/triage_cache.json) — the only
+        # cache backing triage results. Its dir is derived from the in-memory
+        # cache's dir (.vibe/cache -> .vibe); disabled when no real cache dir
+        # is available (e.g. mocked in tests).
+        if triage_cache is not None:
+            self._triage_cache = triage_cache
+        else:
+            cache_dir = getattr(cache_manager, "cache_dir", None)
+            self._triage_cache = (
+                TriageCache(_resolve_vibe_dir(cache_dir))
+                if isinstance(cache_dir, (str, Path))
+                else None
+            )
+        # Embedding recall for the candidate prefilter, persisted alongside
+        # the triage cache (.vibe/skill_embeddings.json). None when no real
+        # cache dir is available; the prefilter then uses KeywordMatcher.
+        if embedding_recall is not None:
+            self._embedding_recall = embedding_recall
+        else:
+            cache_dir = getattr(cache_manager, "cache_dir", None)
+            self._embedding_recall = (
+                EmbeddingRecall(_resolve_vibe_dir(cache_dir))
+                if isinstance(cache_dir, (str, Path))
+                else None
+            )
+        self._last_recall_method: str | None = None
         self._circuit_breaker = TriageCircuitBreaker(
             enabled=getattr(config, "ai_triage_circuit_breaker_enabled", True),
             failure_threshold=getattr(config, "ai_triage_circuit_breaker_failure_threshold", 3),
@@ -75,31 +126,13 @@ class TriageService:
             self._llm = self.init_llm_client()
 
         if self._llm is None or not self._llm.configured():
+            # LLM unconfigured means the whole triage layer is off — including
+            # the persistent cache below ("layer closed = fully closed"), even
+            # though a fresh hit itself would cost nothing.
             return None
 
-        # Budget enforcement
-        budget = getattr(self._config, "ai_triage_budget_monthly", 5.0)
-        if budget > 0:
-            monthly_cost = self._cost_tracker.get_monthly_cost()
-            if monthly_cost >= budget:
-                logger.debug(
-                    f"AI triage skipped: monthly budget exhausted ({monthly_cost:.4f}/{budget:.4f} USD)"
-                )
-                self._circuit_breaker.trip("budget_exhausted")
-                return None
-            if monthly_cost >= budget * 0.9:
-                logger.warning(f"AI triage budget at {monthly_cost:.4f}/{budget:.4f} USD (90%+)")
-
-        # Circuit breaker: fast-fail if recent calls have been slow or failing
-        if not self._circuit_breaker.can_execute():
-            logger.debug("AI triage skipped: circuit breaker is open")
-            return None
-
-        # Cost control: pre-filter candidates with keyword matcher before sending to LLM
-        max_skills = self._config.ai_triage_max_skills
-        triage_candidates = self.prefilter_ai_triage_candidates(query, candidates, max_skills)
-
-        # Build augmented query with memory context
+        # Build augmented query with memory context (before the cache lookup
+        # so the persisted key matches what would be sent to the LLM).
         augmented_query = query
         if (
             context
@@ -115,10 +148,100 @@ class TriageService:
                 + f"\nCurrent request: {query}"
             )
 
-        cache_key = f"ai_triage:{augmented_query}"
-        cached = self._get_cache(cache_key)
-        if cached:
-            return LayerResult(match=cached, layer=RoutingLayer.AI_TRIAGE)
+        # Persistent cross-process cache: fresh entries skip the LLM entirely;
+        # stale ones (expired TTL / changed candidates) are kept as last-good.
+        # A fresh hit costs nothing (no recall, no LLM call), so it runs
+        # before the prefilter and the budget/circuit gates below — those only
+        # guard the LLM call path. The hash covers the FULL candidate set (not
+        # the prefiltered window), which is what makes lookup possible before
+        # prefiltering; a changed set demotes the entry to stale, and
+        # _last_good_route then re-validates the skill still exists.
+        stale_entry: dict[str, Any] | None = None
+        if self._triage_cache is not None:
+            fresh_entry, stale_entry = self._triage_cache.lookup(
+                augmented_query, candidates, self._cache_ttl_hours()
+            )
+            if fresh_entry is not None:
+                try:
+                    skill_id = str(fresh_entry["skill_id"])
+                    # Session-end guard, same criterion as the LLM path below:
+                    # the entry passed the guard when stored, but skill
+                    # triggers may have changed since — re-validate
+                    # defensively. A guarded hit is treated as a miss and
+                    # triage continues down to the gated LLM path.
+                    if self.is_session_end_skill(
+                        skill_id
+                    ) and not self.is_explicit_session_end_signal(query, candidates):
+                        logger.debug(
+                            "Persistent triage hit '%s' ignored: query lacks an explicit session-end signal",
+                            skill_id,
+                        )
+                    else:
+                        route = SkillRoute(
+                            skill_id=skill_id,
+                            confidence=float(fresh_entry["confidence"]),
+                            layer=RoutingLayer.AI_TRIAGE,
+                            source=str(fresh_entry.get("source", "")),
+                            description=str(fresh_entry.get("description", "")),
+                            metadata={
+                                "ai_triage": True,
+                                "persistent_cache": True,
+                                # Cache hit: nothing was sent to the LLM (the
+                                # prefilter below was skipped), so there is no
+                                # real model or parse mode — fixed placeholders
+                                # keep the metadata keys identical to the LLM
+                                # path ("cache" marks the provenance).
+                                "structured": False,
+                                "model": "cache",
+                                "candidates_sent": 0,
+                                "recall_method": None,
+                            },
+                        )
+                        return LayerResult(match=route, layer=RoutingLayer.AI_TRIAGE)
+                except (KeyError, TypeError, ValueError) as e:
+                    logger.debug("Failed to deserialize persistent triage entry: %s", e)
+
+        # Budget enforcement. Cheap check, runs before the (expensive)
+        # prefilter below: a closed gate must not pay the recall cost.
+        budget = getattr(self._config, "ai_triage_budget_monthly", 5.0)
+        if budget > 0:
+            monthly_cost = self._cost_tracker.get_monthly_cost()
+            if monthly_cost >= budget:
+                # The trip below logs the single warning for this path (with
+                # the cost figures in the reason); no separate log here, and
+                # the 90% warning only covers the not-yet-exhausted band.
+                self._circuit_breaker.trip(
+                    f"budget exhausted ({monthly_cost:.4f}/{budget:.4f} USD)"
+                )
+                # Last-good fallback: the budget gate only guards the LLM call;
+                # a stale persistent entry may still be usable while the LLM
+                # path is closed. Aliveness is checked against the full
+                # candidate set (is the skill still installed), not the
+                # prefiltered window.
+                last_good = self._last_good_route(stale_entry, candidates)
+                if last_good is not None:
+                    return LayerResult(match=last_good, layer=RoutingLayer.AI_TRIAGE)
+                return None
+            if monthly_cost >= budget * 0.9:
+                logger.warning(f"AI triage budget at {monthly_cost:.4f}/{budget:.4f} USD (90%+)")
+
+        # Circuit breaker: fast-fail if recent calls have been slow or failing.
+        # Also cheap, so it too precedes the prefilter.
+        if not self._circuit_breaker.can_execute():
+            logger.debug("AI triage skipped: circuit breaker is open")
+            # Last-good fallback: exactly when the LLM keeps failing, a stale
+            # persistent entry is the only usable triage signal left.
+            last_good = self._last_good_route(stale_entry, candidates)
+            if last_good is not None:
+                return LayerResult(match=last_good, layer=RoutingLayer.AI_TRIAGE)
+            return None
+
+        # Cost control: pre-filter candidates (embedding recall, keyword
+        # fallback) before sending to LLM. Only reached on a cache miss with
+        # both gates open — a fresh hit or a closed gate never pays the
+        # recall cost.
+        max_skills = self._config.ai_triage_max_skills
+        triage_candidates = self.prefilter_ai_triage_candidates(query, candidates, max_skills)
 
         def _skill_summary(c: dict[str, Any]) -> str:
             text = c.get("intent", c.get("description", "N/A"))
@@ -131,15 +254,9 @@ class TriageService:
 
         prompt = self.build_ai_triage_prompt(augmented_query, skills_summary)
 
-        import time
-
         start_time = time.perf_counter()
         try:
-            response = self._llm.call(
-                prompt=prompt,
-                max_tokens=self._config.ai_triage_max_tokens,
-                temperature=0.0,
-            )
+            response = self._call_llm(prompt)
             latency_ms = (time.perf_counter() - start_time) * 1000
 
             parsed = self.parse_ai_triage_response(response.content)
@@ -211,14 +328,23 @@ class TriageService:
                             "structured": parsed.get("structured", False),
                             "model": getattr(response, "model", "unknown"),
                             "candidates_sent": len(triage_candidates),
+                            "recall_method": self._last_recall_method,
                         },
                     )
-                    self._set_cache(cache_key, result.to_dict())
+                    if self._triage_cache is not None:
+                        # Hash the full candidate set so a later lookup can
+                        # run before the prefilter (see lookup above).
+                        self._triage_cache.store(augmented_query, candidates, result.to_dict())
                     return LayerResult(match=result, layer=RoutingLayer.AI_TRIAGE)
         except Exception as e:
             latency_ms = (time.perf_counter() - start_time) * 1000
             logger.debug(f"AI triage failed, falling through to next layer: {e}")
             self._circuit_breaker.record_failure(latency_ms, reason=str(e))
+            # Last-good fallback: LLM failed but a stale persistent entry
+            # (expired TTL / changed candidates) may still be usable.
+            last_good = self._last_good_route(stale_entry, candidates)
+            if last_good is not None:
+                return LayerResult(match=last_good, layer=RoutingLayer.AI_TRIAGE)
 
         return None
 
@@ -228,23 +354,36 @@ class TriageService:
         candidates: list[dict[str, Any]],
         max_skills: int,
     ) -> list[dict[str, Any]]:
-        """Pre-filter candidates for AI Triage using fast keyword matching.
+        """Pre-filter candidates for AI Triage, embedding recall first.
 
         Excludes management-only skills (slash-*) from semantic matching.
-        Instead of sending all candidates to the LLM (wasteful), we use the
-        KeywordMatcher to rank them by relevance and only send the top N.
+        Instead of sending all candidates to the LLM (wasteful), we rank
+        them by embedding similarity and only send the top N. Any recall
+        failure falls back to KeywordMatcher ranking, identical to the
+        previous behavior.
         """
         eligible = [c for c in candidates if not c.get("management_only")]
+        self._last_recall_method = None
         if len(eligible) <= max_skills:
             return eligible
 
-        matcher_config = MatcherConfig(
-            min_confidence=0.0,
-            use_cache=False,
+        recall_ids = (
+            self._embedding_recall.recall(query, eligible, max_skills)
+            if self._embedding_recall is not None
+            else None
         )
-        matcher = KeywordMatcher(matcher_config)
-        matches = matcher.match(query, eligible, top_k=max_skills)
-        matched_ids = {m.skill_id for m in matches}
+        if recall_ids is not None:
+            matched_ids = set(recall_ids)
+            self._last_recall_method = "embedding"
+        else:
+            matcher_config = MatcherConfig(
+                min_confidence=0.0,
+                use_cache=False,
+            )
+            matcher = KeywordMatcher(matcher_config)
+            matches = matcher.match(query, eligible, top_k=max_skills)
+            matched_ids = {m.skill_id for m in matches}
+            self._last_recall_method = "keyword"
 
         # Preserve original order for matched candidates, then backfill if needed
         prefiltered = [c for c in eligible if c["id"] in matched_ids]
@@ -381,21 +520,97 @@ class TriageService:
 
         return result
 
-    def _get_cache(self, key: str) -> SkillRoute | None:
-        data = self._cache_manager.get(key)
-        if data:
+    def _cache_ttl_hours(self) -> float:
+        """Persistent-cache TTL in hours (default 72); tolerant of mocks."""
+        ttl = getattr(self._config, "triage_cache_ttl_hours", 72)
+        return float(ttl) if isinstance(ttl, (int, float)) else 72.0
+
+    def _call_llm(self, prompt: str) -> Any:
+        """Call the LLM with a hard timeout (config: ai_triage_timeout_seconds).
+
+        Provider clients carry their own hardcoded transport timeouts (~30s);
+        this caps the whole triage call lower for interactive routing. The
+        worker thread is a daemon so a timed-out call never blocks CLI exit.
+        """
+        timeout_s = getattr(self._config, "ai_triage_timeout_seconds", 15.0)
+        if not isinstance(timeout_s, (int, float)):
+            timeout_s = 15.0
+        outcome: dict[str, Any] = {}
+
+        def _run() -> None:
             try:
-                return SkillRoute(
-                    skill_id=data["skill_id"],
-                    confidence=data["confidence"],
-                    layer=RoutingLayer(data["layer"]),
-                    source=data["source"],
-                    description=data.get("description", ""),
-                    metadata=data.get("metadata", {}),
+                outcome["response"] = self._llm.call(
+                    prompt=prompt,
+                    max_tokens=self._config.ai_triage_max_tokens,
+                    temperature=0.0,
                 )
-            except (KeyError, TypeError) as e:
-                logger.debug(f"Failed to deserialize cached SkillRoute: {e}")
-        return None
-
-    def _set_cache(self, key: str, data: dict[str, Any]) -> None:
-        self._cache_manager.set(key, data, ttl=3600)
+            except Exception as e:  # surfaced on the caller thread below
+                outcome["error"] = e
+
+        worker = threading.Thread(target=_run, daemon=True)
+        worker.start()
+        worker.join(float(timeout_s))
+        if worker.is_alive():
+            # The daemon worker is left running: the provider call may still
+            # complete (and be billed) after we time out here, but that cost
+            # is never recorded by the cost tracker.
+            raise TimeoutError(f"AI triage LLM call exceeded {timeout_s}s")
+        if "error" in outcome:
+            raise outcome["error"]
+        return outcome["response"]
+
+    @staticmethod
+    def _skill_in_candidates(skill_id: str, candidates: list[dict[str, Any]]) -> bool:
+        """Case-tolerant membership check against the candidate id set."""
+        if any(c.get("id") == skill_id for c in candidates):
+            return True
+        lowered = skill_id.lower()
+        return any(str(c.get("id", "")).lower() == lowered for c in candidates)
+
+    def _last_good_route(
+        self,
+        stale_entry: dict[str, Any] | None,
+        candidates: list[dict[str, Any]],
+    ) -> SkillRoute | None:
+        """Build a last-good route from a stale persistent entry.
+
+        Only used when the LLM path is unavailable (call failed, circuit
+        open, or budget exhausted); the stale skill must still exist in the
+        full current candidate set — i.e. still installed — not merely in the
+        prefiltered top-N window (a removed skill is never resurrected).
+
+        The recorded confidence is decayed (×LAST_GOOD_CONFIDENCE_DECAY) so a
+        stale result never competes with a fresh LLM result at full weight;
+        the original value is kept in metadata as
+        ``last_good_original_confidence``. The decayed
+        confidence may fall below the router's min_confidence and be rejected
+        downstream (unified.py) — that is intentional: a stale result should
+        not auto-execute. The ``last_good`` metadata flag lets downstream
+        consumers distinguish it from a fresh result.
+        """
+        if not stale_entry:
+            return None
+        try:
+            skill_id = str(stale_entry["skill_id"])
+            if not self._skill_in_candidates(skill_id, candidates):
+                return None
+            original_confidence = float(stale_entry["confidence"])
+            return SkillRoute(
+                skill_id=skill_id,
+                confidence=original_confidence * LAST_GOOD_CONFIDENCE_DECAY,
+                layer=RoutingLayer.AI_TRIAGE,
+                source=str(stale_entry.get("source", "")),
+                description=str(stale_entry.get("description", "")),
+                metadata={
+                    "ai_triage": True,
+                    "last_good": True,
+                    "last_good_original_confidence": original_confidence,
+                    # Last-good: nothing was sent to the LLM (the gates
+                    # closed or the call failed before a new prompt).
+                    "candidates_sent": 0,
+                    "recall_method": self._last_recall_method,
+                },
+            )
+        except (KeyError, TypeError, ValueError) as e:
+            logger.debug("Failed to build last-good route: %s", e)
+            return None
diff --git a/src/vibesop/core/routing/unified.py b/src/vibesop/core/routing/unified.py
index 08417a5..874b4a2 100644
--- a/src/vibesop/core/routing/unified.py
+++ b/src/vibesop/core/routing/unified.py
@@ -66,6 +66,51 @@ if TYPE_CHECKING:
 
 logger = logging.getLogger(__name__)
 
+# Harness-injected context marker (e.g. Kimi Code / Claude Code system
+# reminders). Production logs showed <system-reminder> blocks reaching
+# route() as if they were user queries, producing garbage matches and
+# polluting miss analytics. Junk queries are rejected at the routing entry
+# point with a no-match result, before any matching layer, telemetry, or
+# analytics write. (Constant, not config: there is no legitimate reason to
+# route harness markup.)
+_SYSTEM_REMINDER_MARKER = "<system-reminder"
+
+
+def _is_junk_query(query: str) -> bool:
+    """True when the query IS harness markup, not when it merely mentions it.
+
+    Criterion: the query (ignoring leading whitespace) starts with the
+    ``<system-reminder`` marker. The injection shape seen in production logs
+    is the whole query being a reminder block, so a prefix check catches it.
+    A plain substring match was rejected: it also kills legitimate queries
+    that literally discuss the marker (e.g. developing this repo's own junk
+    filter).
+    """
+    return query.lstrip().startswith(_SYSTEM_REMINDER_MARKER)
+
+
+def _junk_query_result(query: str) -> RoutingResult:
+    """No-match result for harness-markup junk queries.
+
+    Shared by the route() entry guard and the _single_skill_route() head
+    guard: same primary=None shape as fallback_mode="disabled" (minus the
+    matcher-pipeline nearest scan, which would be meaningless for markup).
+    """
+    return RoutingResult(
+        primary=None,
+        alternatives=[],
+        routing_path=[],
+        layer_details=[
+            LayerDetail(
+                layer=RoutingLayer.NO_MATCH,
+                matched=False,
+                reason="Query rejected: contains <system-reminder> harness markup, not a user query",
+            )
+        ],
+        query=query,
+        duration_ms=0.0,
+    )
+
 
 def _maybe_wrap_for_spans(provider: Any) -> Any:
     """Best-effort wrap an injected provider with SpanWrappedProvider.
@@ -157,6 +202,12 @@ class UnifiedRouter(
         self.project_root = Path(project_root).resolve()
         self._llm_factory = llm_factory
         self._prompt_builder = prompt_builder
+        if prompt_builder is None:
+            logger.warning(
+                "No prompt_builder provided; AI triage will use the minimal "
+                "fallback prompt ('Query: ... Select best skill.'), which the "
+                "LLM may answer as chat, so skill selection is likely to fail."
+            )
         if skill_loader is not None:
             self._skill_loader = skill_loader
 
@@ -408,6 +459,14 @@ class UnifiedRouter(
         context: RoutingContext | None = None,
     ) -> RoutingResult:
         """Internal: route a query to the best matching skill."""
+        # Junk guard (defense in depth): Orchestrator, session context, and
+        # PlanBuilder call this method directly, bypassing route()'s entry
+        # guard, so the same rejection lives here too — before stats,
+        # tracing, and any matching layer. route()'s own guard is kept: it
+        # sits before the telemetry block and additionally skips the
+        # analytics / miss-counter writes.
+        if _is_junk_query(query):
+            return _junk_query_result(query)
         start_time = time.perf_counter()
         with self._stats_lock:
             self._total_routes += 1
@@ -543,7 +602,17 @@ class UnifiedRouter(
         early_match = self._try_early_layers(
             query, early_candidates, routing_path, layer_details, use_keyword
         )
-        if early_match is not None:
+        scenario_candidate: SkillRoute | None = None
+        if early_match is not None and early_match.layer == RoutingLayer.SCENARIO:
+            # Scenario hits are pure keyword-regex matches at a fixed 0.9
+            # confidence, so they used to win every best-of and short-circuit
+            # the cascade — shelving AI triage, the only semantic layer, and
+            # misrouting real queries (e.g. "全面审查这个仓库的代码质量").
+            # A scenario hit is now only a candidate: AI triage arbitrates,
+            # and the scenario match is used only as fallback when triage
+            # produces nothing (see below).
+            scenario_candidate = early_match
+        elif early_match is not None:
             self._record_layer(early_match.layer)
             return self._build_match_result(
                 query,
@@ -558,19 +627,31 @@ class UnifiedRouter(
                 context,
             )
 
-        # Step 2: AI Triage (force for long/LLM queries, normal for keyword)
+        # Step 2: AI Triage (force for long/LLM queries, normal for keyword).
+        # A pending scenario candidate also forces triage: scenario-matching
+        # queries are exactly the ambiguity hot spots where the short-query
+        # bypass does not apply — bypassing here would let the fixed-0.9
+        # regex hit win through the fallback below without any semantic
+        # arbitration (the original "全面审查这个仓库的代码质量" misroute).
         match, detail = _layers.try_ai_triage_layer(
             self,
             query,
             candidates,
             context,  # pyright: ignore[reportArgumentType]
-            force=not use_keyword,
+            force=(not use_keyword) or (scenario_candidate is not None),
         )
         routing_path.append(RoutingLayer.AI_TRIAGE)
         layer_details.append(detail)
         self._tracer.record_layer(RoutingLayer.AI_TRIAGE, detail, len(candidates))
         if match and match.confidence >= self._config.min_confidence:
             self._record_layer(RoutingLayer.AI_TRIAGE)
+            if scenario_candidate is not None:
+                # Triage arbitrated over a pending scenario candidate and won:
+                # scenario still participated in this routing decision, so
+                # count it — otherwise layer stats under-report scenario
+                # involvement. (The scenario_fallback branch below records
+                # its own count; this branch is mutually exclusive with it.)
+                self._record_layer(RoutingLayer.SCENARIO)
             return self._build_match_result(
                 query,
                 match,
@@ -584,6 +665,29 @@ class UnifiedRouter(
                 context,
             )
 
+        # Scenario fallback: a scenario hit forces triage above (the
+        # short-query bypass is skipped for it), so landing here means
+        # triage actually ran — or tried to — and produced nothing usable
+        # (unavailable, error, or below min_confidence). The demoted
+        # scenario match then becomes the result. The fallback is flagged
+        # so downstream consumers can tell "scenario won by default" from
+        # a triage-arbitrated match.
+        if scenario_candidate is not None:
+            scenario_candidate.metadata["scenario_fallback"] = True
+            self._record_layer(RoutingLayer.SCENARIO)
+            return self._build_match_result(
+                query,
+                scenario_candidate,
+                [],
+                routing_path,
+                layer_details,
+                start_time,
+                deprecated_warnings,
+                conversation,
+                original_query,
+                context,
+            )
+
         # Step 3: Matcher pipeline (shared fallback)
         primary, alternatives, detail = _pipeline.run_matcher_pipeline(
             self, query, candidates, context, collect_rejected=True
@@ -624,9 +728,9 @@ class UnifiedRouter(
             self._tracer.record_layer(RoutingLayer.SCENARIO, scen_detail, len(candidates))
 
             idx_match, idx_detail = _layers.try_index_layer(self, query, candidates)  # pyright: ignore[reportArgumentType]
-            routing_path.append(RoutingLayer.AI_TRIAGE)
+            routing_path.append(RoutingLayer.SEMANTIC_INDEX)
             layer_details.append(idx_detail)
-            self._tracer.record_layer(RoutingLayer.AI_TRIAGE, idx_detail, len(candidates))
+            self._tracer.record_layer(RoutingLayer.SEMANTIC_INDEX, idx_detail, len(candidates))
 
             best = max(
                 (m for m in (scen_match, idx_match) if m is not None),
@@ -638,9 +742,9 @@ class UnifiedRouter(
         else:
             # Index standalone
             match, detail = _layers.try_index_layer(self, query, candidates)  # pyright: ignore[reportArgumentType]
-            routing_path.append(RoutingLayer.AI_TRIAGE)
+            routing_path.append(RoutingLayer.SEMANTIC_INDEX)
             layer_details.append(detail)
-            self._tracer.record_layer(RoutingLayer.AI_TRIAGE, detail, len(candidates))
+            self._tracer.record_layer(RoutingLayer.SEMANTIC_INDEX, detail, len(candidates))
             if match and match.confidence >= self._config.min_confidence:
                 return match
 
@@ -830,6 +934,13 @@ class UnifiedRouter(
         Returns:
             RoutingResult with primary match or no-match sentinel.
         """
+        # Junk guard: reject harness-injected <system-reminder> content before
+        # it reaches any matching layer. Returns the same primary=None no-match
+        # shape as fallback_mode="disabled" (minus the matcher-pipeline nearest
+        # scan, which would be meaningless for markup), and skips the telemetry
+        # block below so junk never lands in analytics / the miss counter.
+        if _is_junk_query(query):
+            return _junk_query_result(query)
         result = self._single_skill_route(query, candidates, context)
         # P1 telemetry — the single exit point for the single-route path (hit,
         # low-confidence, and no-match/fallback all land here). Both writes are
diff --git a/tests/core/routing/test_index_layer.py b/tests/core/routing/test_index_layer.py
index e3ea9fd..5cefd87 100644
--- a/tests/core/routing/test_index_layer.py
+++ b/tests/core/routing/test_index_layer.py
@@ -6,6 +6,9 @@ import json
 from pathlib import Path
 from unittest.mock import MagicMock, patch
 
+from vibesop.core.config.manager import RoutingConfig
+from vibesop.core.models import LayerDetail, RoutingLayer
+from vibesop.core.routing import UnifiedRouter
 from vibesop.core.routing._layers import (
     _compute_index_score,
     _tokenize_query,
@@ -28,18 +31,43 @@ class TestTokenizeQuery:
 
     def test_cjk_characters(self) -> None:
         tokens = _tokenize_query("帮我审查代码")
-        assert "帮" in tokens
-        assert "审" in tokens
-        assert "查" in tokens
-        assert "代" in tokens
-        assert "码" in tokens
+        # CJK is tokenized as bigrams over contiguous runs
+        assert "帮我" in tokens
+        assert "我审" in tokens
+        assert "审查" in tokens
+        assert "查代" in tokens
+        assert "代码" in tokens
+        # Single chars are no longer tokens for multi-char runs
+        assert "帮" not in tokens
+        assert "审" not in tokens
+
+    def test_single_cjk_char_keeps_unigram(self) -> None:
+        tokens = _tokenize_query("好")
+        assert tokens == {"好"}
+
+    def test_cjk_run_separated_by_non_cjk(self) -> None:
+        # Non-CJK characters break runs: no bigram may bridge across them
+        tokens = _tokenize_query("提交PR代码")
+        assert "提交" in tokens
+        assert "代码" in tokens
+        assert "交代" not in tokens
+
+    def test_cjk_bigram_reduces_spurious_overlap(self) -> None:
+        # "提交代码" vs "提交PR": unigram tokenization shared every char;
+        # bigrams share only the leading "提交".
+        commit_tokens = _tokenize_query("提交代码")
+        pr_tokens = _tokenize_query("提交PR")
+        assert commit_tokens & pr_tokens == {"提交"}
+        assert len(commit_tokens & pr_tokens) < len(commit_tokens) / 2
 
     def test_mixed_text(self) -> None:
         tokens = _tokenize_query("review 代码 security 审查")
         assert "review" in tokens
         assert "security" in tokens
-        assert "代" in tokens
-        assert "审" in tokens
+        assert "代码" in tokens
+        assert "审查" in tokens
+        assert "代" not in tokens
+        assert "审" not in tokens
 
 
 class TestComputeIndexScore:
@@ -278,15 +306,70 @@ class TestEmbeddingFallback:
         }
         index_path.write_text(json.dumps(index_data), encoding="utf-8")
 
-        # Ensure sentence_transformers is NOT importable by removing any mock
-        # that earlier tests may have injected into sys.modules.
-        _saved = sys.modules.pop("sentence_transformers", None)
-        try:
+        # Simulate sentence-transformers being uninstalled: a None entry in
+        # sys.modules makes any import of the package raise ImportError,
+        # regardless of whether it is actually installed in this environment.
+        with patch.dict(sys.modules, {"sentence_transformers": None}):
             match, detail = try_index_layer(router, "audit the auth flow", [])
-        finally:
-            if _saved is not None:
-                sys.modules["sentence_transformers"] = _saved
 
         assert match is None
         assert detail.matched is False
         assert "not available" in detail.reason.lower()
+
+
+class TestEarlyLayersRoutingPath:
+    """Regression: the semantic index layer must be recorded as SEMANTIC_INDEX
+    in routing_path and traces, not mislabeled as AI_TRIAGE (M1a)."""
+
+    def _make_router(self, tmp_path: Path) -> UnifiedRouter:
+        config = RoutingConfig(enable_ai_triage=False)
+        return UnifiedRouter(project_root=tmp_path, config=config)
+
+    def test_keyword_branch_records_semantic_index(self, tmp_path: Path) -> None:
+        """Scenario+index best-of branch: index layer is SEMANTIC_INDEX."""
+        router = self._make_router(tmp_path)
+        router._tracer.enabled = True
+        router._tracer.start_trace("review code")
+
+        routing_path: list[RoutingLayer] = []
+        layer_details: list[LayerDetail] = []
+        scen_detail = LayerDetail(layer=RoutingLayer.SCENARIO, matched=False, reason="miss")
+        idx_detail = LayerDetail(layer=RoutingLayer.SEMANTIC_INDEX, matched=False, reason="miss")
+
+        with (
+            patch(
+                "vibesop.core.routing._layers.try_scenario_layer",
+                return_value=(None, scen_detail),
+            ),
+            patch(
+                "vibesop.core.routing._layers.try_index_layer",
+                return_value=(None, idx_detail),
+            ),
+        ):
+            router._try_early_layers("review code", [], routing_path, layer_details, use_keyword=True)
+
+        assert routing_path == [RoutingLayer.SCENARIO, RoutingLayer.SEMANTIC_INDEX]
+        assert RoutingLayer.AI_TRIAGE not in routing_path
+        traced = [lt.layer for lt in router._tracer._current.layers]  # type: ignore[union-attr]
+        assert traced == ["scenario", "semantic_index"]
+
+    def test_llm_branch_records_semantic_index(self, tmp_path: Path) -> None:
+        """Index-standalone branch: index layer is SEMANTIC_INDEX."""
+        router = self._make_router(tmp_path)
+        router._tracer.enabled = True
+        router._tracer.start_trace("review code")
+
+        routing_path: list[RoutingLayer] = []
+        layer_details: list[LayerDetail] = []
+        idx_detail = LayerDetail(layer=RoutingLayer.SEMANTIC_INDEX, matched=False, reason="miss")
+
+        with patch(
+            "vibesop.core.routing._layers.try_index_layer",
+            return_value=(None, idx_detail),
+        ):
+            router._try_early_layers("review code", [], routing_path, layer_details, use_keyword=False)
+
+        assert routing_path == [RoutingLayer.SEMANTIC_INDEX]
+        assert RoutingLayer.AI_TRIAGE not in routing_path
+        traced = [lt.layer for lt in router._tracer._current.layers]  # type: ignore[union-attr]
+        assert traced == ["semantic_index"]

## build_eval_from_logs.py merge 段(未跟踪新文件)
            "needs_review": True,
        }
        if skill:
            entry["weak_label"] = True
        entries.append(entry)
    return entries


def merge_confirmed(extended_path: Path, main_path: Path = MAIN_EVAL) -> int:
    """Append human-confirmed entries (needs_review: false, expect set)
    from the extended file into the main eval set, and drop them from the
    extended file. Returns the number of merged entries."""
    extended = yaml.safe_load(extended_path.read_text(encoding="utf-8")) or []
    main = yaml.safe_load(main_path.read_text(encoding="utf-8")) or []
    main_bad = [e for e in main if not isinstance(e.get("query"), str)]
    if main_bad:
        # Hand-edited main entries missing "query" can't be keyed — skip
        # them for dedup instead of crashing with KeyError.
        print(
            f"Warning: skipped {len(main_bad)} main entries missing 'query'.",
            file=sys.stderr,
        )
    main_queries = {normalize(e["query"]) for e in main if isinstance(e.get("query"), str)}

    confirmed, remaining, skipped = [], [], 0
    for e in extended:
        if not isinstance(e.get("query"), str):
            # Hand-edited entries missing "query" can't be keyed — keep them
            # in the extended file instead of crashing mid-merge.
            skipped += 1
            remaining.append(e)
        elif e.get("needs_review") is False and e.get("expect"):
            if normalize(e["query"]) not in main_queries:
                confirmed.append(
                    {k: v for k, v in e.items() if k not in ("needs_review", "weak_label")}
                )
                main_queries.add(normalize(e["query"]))
        else:
            remaining.append(e)
    if skipped:
        print(
            f"Warning: skipped {skipped} extended entries missing 'query'.",
            file=sys.stderr,
        )

    if confirmed:
