# 门禁4b 复审包:pi nit 修复(hash 口径 + lookup 前提)

## 修复内容
1. TriageCache lookup/store 的 candidates_hash 改基于全候选集;lookup 提到 prefilter 之前(fresh 命中零召回成本);prefilter 移到 gate 之前、lookup 之后。
2. _last_good_route 存活校验改对全量 candidates(原来对 prefilter top-N)。
3. fresh 命中 metadata:candidates_sent=0、recall_method=None(准确化,无下游消费)。
4. configured()=False 注释改准确;衰减 0.7 提为 LAST_GOOD_CONFIDENCE_DECAY 常量。

## 新顺序
enable/configured 检查 → augmented_query → lookup(全量) → fresh 命中返回 → prefilter → budget/circuit gate(带 last-good) → LLM → store(全量)

## diff: triage_service.py
diff --git a/src/vibesop/core/routing/triage_service.py b/src/vibesop/core/routing/triage_service.py
index 8a2a8d5..093e7bd 100644
--- a/src/vibesop/core/routing/triage_service.py
+++ b/src/vibesop/core/routing/triage_service.py
@@ -4,6 +4,8 @@ from __future__ import annotations
 
 import logging
 import os
+import threading
+from pathlib import Path
 from typing import TYPE_CHECKING, Any
 
 from vibesop.core.matching import KeywordMatcher, MatcherConfig
@@ -11,6 +13,8 @@ from vibesop.core.models import RoutingLayer, SkillRoute
 from vibesop.core.routing._protocols import LLMFactory, PromptBuilder
 from vibesop.core.routing.circuit_breaker import TriageCircuitBreaker
 from vibesop.core.routing.layers import LayerResult
+from vibesop.core.routing.triage_cache import TriageCache
+from vibesop.core.routing.triage_recall import EmbeddingRecall
 
 if TYPE_CHECKING:
     from collections.abc import Callable
@@ -22,6 +26,10 @@ if TYPE_CHECKING:
 
 logger = logging.getLogger(__name__)
 
+# Decay applied to a stale (last-good) cached confidence so it never competes
+# with a fresh LLM result at full weight.
+LAST_GOOD_CONFIDENCE_DECAY = 0.7
+
 
 class TriageService:
     """AI Triage layer for skill routing."""
@@ -35,15 +43,46 @@ class TriageService:
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
+                TriageCache(Path(cache_dir).parent)
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
+                EmbeddingRecall(Path(cache_dir).parent)
+                if isinstance(cache_dir, (str, Path))
+                else None
+            )
+        self._last_recall_method: str | None = None
         self._circuit_breaker = TriageCircuitBreaker(
             enabled=getattr(config, "ai_triage_circuit_breaker_enabled", True),
             failure_threshold=getattr(config, "ai_triage_circuit_breaker_failure_threshold", 3),
@@ -75,8 +114,68 @@ class TriageService:
             self._llm = self.init_llm_client()
 
         if self._llm is None or not self._llm.configured():
+            # LLM unconfigured means the whole triage layer is off — including
+            # the persistent cache below ("layer closed = fully closed"), even
+            # though a fresh hit itself would cost nothing.
             return None
 
+        # Build augmented query with memory context (before the cache lookup
+        # so the persisted key matches what would be sent to the LLM).
+        augmented_query = query
+        if (
+            context
+            and context.recent_queries
+            and (
+                len(query) < 20
+                or any(p in query.lower() for p in ("还是", "再", "继续", "也", "另外", "还有"))
+            )
+        ):
+            augmented_query = (
+                "Conversation:\n"
+                + "\n".join(f"- {q}" for q in context.recent_queries[-3:])
+                + f"\nCurrent request: {query}"
+            )
+
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
+                    route = SkillRoute(
+                        skill_id=str(fresh_entry["skill_id"]),
+                        confidence=float(fresh_entry["confidence"]),
+                        layer=RoutingLayer.AI_TRIAGE,
+                        source=str(fresh_entry.get("source", "")),
+                        description=str(fresh_entry.get("description", "")),
+                        metadata={
+                            "ai_triage": True,
+                            "persistent_cache": True,
+                            # Cache hit: no recall ran and nothing was sent to
+                            # the LLM (the prefilter below was skipped).
+                            "candidates_sent": 0,
+                            "recall_method": None,
+                        },
+                    )
+                    return LayerResult(match=route, layer=RoutingLayer.AI_TRIAGE)
+                except (KeyError, TypeError, ValueError) as e:
+                    logger.debug("Failed to deserialize persistent triage entry: %s", e)
+
+        # Cost control: pre-filter candidates (embedding recall, keyword
+        # fallback) before sending to LLM. Only reached on a cache miss — a
+        # fresh hit above never pays the recall cost.
+        max_skills = self._config.ai_triage_max_skills
+        triage_candidates = self.prefilter_ai_triage_candidates(query, candidates, max_skills)
+
         # Budget enforcement
         budget = getattr(self._config, "ai_triage_budget_monthly", 5.0)
         if budget > 0:
@@ -86,6 +185,14 @@ class TriageService:
                     f"AI triage skipped: monthly budget exhausted ({monthly_cost:.4f}/{budget:.4f} USD)"
                 )
                 self._circuit_breaker.trip("budget_exhausted")
+                # Last-good fallback: the budget gate only guards the LLM call;
+                # a stale persistent entry may still be usable while the LLM
+                # path is closed. Aliveness is checked against the full
+                # candidate set (is the skill still installed), not the
+                # prefiltered window.
+                last_good = self._last_good_route(stale_entry, candidates)
+                if last_good is not None:
+                    return LayerResult(match=last_good, layer=RoutingLayer.AI_TRIAGE)
                 return None
             if monthly_cost >= budget * 0.9:
                 logger.warning(f"AI triage budget at {monthly_cost:.4f}/{budget:.4f} USD (90%+)")
@@ -93,33 +200,13 @@ class TriageService:
         # Circuit breaker: fast-fail if recent calls have been slow or failing
         if not self._circuit_breaker.can_execute():
             logger.debug("AI triage skipped: circuit breaker is open")
+            # Last-good fallback: exactly when the LLM keeps failing, a stale
+            # persistent entry is the only usable triage signal left.
+            last_good = self._last_good_route(stale_entry, candidates)
+            if last_good is not None:
+                return LayerResult(match=last_good, layer=RoutingLayer.AI_TRIAGE)
             return None
 
-        # Cost control: pre-filter candidates with keyword matcher before sending to LLM
-        max_skills = self._config.ai_triage_max_skills
-        triage_candidates = self.prefilter_ai_triage_candidates(query, candidates, max_skills)
-
-        # Build augmented query with memory context
-        augmented_query = query
-        if (
-            context
-            and context.recent_queries
-            and (
-                len(query) < 20
-                or any(p in query.lower() for p in ("还是", "再", "继续", "也", "另外", "还有"))
-            )
-        ):
-            augmented_query = (
-                "Conversation:\n"
-                + "\n".join(f"- {q}" for q in context.recent_queries[-3:])
-                + f"\nCurrent request: {query}"
-            )
-
-        cache_key = f"ai_triage:{augmented_query}"
-        cached = self._get_cache(cache_key)
-        if cached:
-            return LayerResult(match=cached, layer=RoutingLayer.AI_TRIAGE)
-
         def _skill_summary(c: dict[str, Any]) -> str:
             text = c.get("intent", c.get("description", "N/A"))
             triggers = c.get("triggers", [])
@@ -135,11 +222,7 @@ class TriageService:
 
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
@@ -211,14 +294,23 @@ class TriageService:
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
 
@@ -228,23 +320,36 @@ class TriageService:
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
@@ -381,21 +486,92 @@ class TriageService:
 
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
+                    "candidates_sent": len(candidates),
+                    "recall_method": self._last_recall_method,
+                },
+            )
+        except (KeyError, TypeError, ValueError) as e:
+            logger.debug("Failed to build last-good route: %s", e)
+            return None
