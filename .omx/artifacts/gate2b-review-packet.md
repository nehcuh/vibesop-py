# 门禁2 复审(第二轮):BLOCK 项修复

## 修复说明
门禁2 第一轮:pi BLOCK(B1 内存缓存绕过候选集失效),claude 指出持久缓存查找在熔断/预算 gate 之后。本轮只审修复是否正确闭合这两个问题,以及开发者声明的附带行为变化。

## 开发者声明(需裁决)
1. 内存缓存存活校验用全量 candidates,last-good 用 prefilter 后候选集——判据相同集合不同,有意为之。
2. 内存缓存命中随块上移到 budget/circuit gate 之前(零成本,语义一致)。

## diff: triage_service.py
diff --git a/src/vibesop/core/routing/triage_service.py b/src/vibesop/core/routing/triage_service.py
index 8a2a8d5..8ded8e7 100644
--- a/src/vibesop/core/routing/triage_service.py
+++ b/src/vibesop/core/routing/triage_service.py
@@ -4,6 +4,8 @@ from __future__ import annotations
 
 import logging
 import os
+import threading
+from pathlib import Path
 from typing import TYPE_CHECKING, Any
 
 from vibesop.core.matching import KeywordMatcher, MatcherConfig
@@ -11,6 +13,7 @@ from vibesop.core.models import RoutingLayer, SkillRoute
 from vibesop.core.routing._protocols import LLMFactory, PromptBuilder
 from vibesop.core.routing.circuit_breaker import TriageCircuitBreaker
 from vibesop.core.routing.layers import LayerResult
+from vibesop.core.routing.triage_cache import TriageCache
 
 if TYPE_CHECKING:
     from collections.abc import Callable
@@ -35,6 +38,7 @@ class TriageService:
         get_skill_source: Callable[..., str],
         llm_factory: LLMFactory | None = None,
         prompt_builder: PromptBuilder | None = None,
+        triage_cache: TriageCache | None = None,
     ) -> None:
         self._config = config
         self._cost_tracker = cost_tracker
@@ -44,6 +48,18 @@ class TriageService:
         self._llm_factory = llm_factory
         self._prompt_builder = prompt_builder
         self._llm: Any | None = None
+        # Persistent cross-process cache (.vibe/triage_cache.json). Derived
+        # from the in-memory cache's dir (.vibe/cache -> .vibe); disabled when
+        # no real cache dir is available (e.g. mocked in tests).
+        if triage_cache is not None:
+            self._triage_cache = triage_cache
+        else:
+            cache_dir = getattr(cache_manager, "cache_dir", None)
+            self._triage_cache = (
+                TriageCache(Path(cache_dir).parent)
+                if isinstance(cache_dir, (str, Path))
+                else None
+            )
         self._circuit_breaker = TriageCircuitBreaker(
             enabled=getattr(config, "ai_triage_circuit_breaker_enabled", True),
             failure_threshold=getattr(config, "ai_triage_circuit_breaker_failure_threshold", 3),
@@ -77,24 +93,6 @@ class TriageService:
         if self._llm is None or not self._llm.configured():
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
         # Cost control: pre-filter candidates with keyword matcher before sending to LLM
         max_skills = self._config.ai_triage_max_skills
         triage_candidates = self.prefilter_ai_triage_candidates(query, candidates, max_skills)
@@ -117,8 +115,62 @@ class TriageService:
 
         cache_key = f"ai_triage:{augmented_query}"
         cached = self._get_cache(cache_key)
-        if cached:
-            return LayerResult(match=cached, layer=RoutingLayer.AI_TRIAGE)
+        if cached is not None:
+            # The in-memory cache key ignores the candidate set, so a
+            # long-lived process could keep serving a skill that was since
+            # uninstalled. Honor the hit only if the skill is still a
+            # candidate (same aliveness check as the last-good fallback).
+            if self._skill_in_candidates(cached.skill_id, candidates):
+                return LayerResult(match=cached, layer=RoutingLayer.AI_TRIAGE)
+            logger.debug(
+                "In-memory triage cache hit for removed skill '%s'; treating as miss",
+                cached.skill_id,
+            )
+
+        # Persistent cross-process cache: fresh entries skip the LLM entirely;
+        # stale ones (expired TTL / changed candidates) are kept as last-good.
+        # A fresh hit costs nothing (no LLM call), so it runs before the
+        # budget/circuit gates below — those only guard the LLM call path.
+        stale_entry: dict[str, Any] | None = None
+        if self._triage_cache is not None:
+            fresh_entry, stale_entry = self._triage_cache.lookup(
+                augmented_query, triage_candidates, self._cache_ttl_hours()
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
+                            "candidates_sent": len(triage_candidates),
+                        },
+                    )
+                    return LayerResult(match=route, layer=RoutingLayer.AI_TRIAGE)
+                except (KeyError, TypeError, ValueError) as e:
+                    logger.debug("Failed to deserialize persistent triage entry: %s", e)
+
+        # Budget enforcement
+        budget = getattr(self._config, "ai_triage_budget_monthly", 5.0)
+        if budget > 0:
+            monthly_cost = self._cost_tracker.get_monthly_cost()
+            if monthly_cost >= budget:
+                logger.debug(
+                    f"AI triage skipped: monthly budget exhausted ({monthly_cost:.4f}/{budget:.4f} USD)"
+                )
+                self._circuit_breaker.trip("budget_exhausted")
+                return None
+            if monthly_cost >= budget * 0.9:
+                logger.warning(f"AI triage budget at {monthly_cost:.4f}/{budget:.4f} USD (90%+)")
+
+        # Circuit breaker: fast-fail if recent calls have been slow or failing
+        if not self._circuit_breaker.can_execute():
+            logger.debug("AI triage skipped: circuit breaker is open")
+            return None
 
         def _skill_summary(c: dict[str, Any]) -> str:
             text = c.get("intent", c.get("description", "N/A"))
@@ -135,11 +187,7 @@ class TriageService:
 
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
@@ -214,11 +262,20 @@ class TriageService:
                         },
                     )
                     self._set_cache(cache_key, result.to_dict())
+                    if self._triage_cache is not None:
+                        self._triage_cache.store(
+                            augmented_query, triage_candidates, result.to_dict()
+                        )
                     return LayerResult(match=result, layer=RoutingLayer.AI_TRIAGE)
         except Exception as e:
             latency_ms = (time.perf_counter() - start_time) * 1000
             logger.debug(f"AI triage failed, falling through to next layer: {e}")
             self._circuit_breaker.record_failure(latency_ms, reason=str(e))
+            # Last-good fallback: LLM failed but a stale persistent entry
+            # (expired TTL / changed candidates) may still be usable.
+            last_good = self._last_good_route(stale_entry, triage_candidates)
+            if last_good is not None:
+                return LayerResult(match=last_good, layer=RoutingLayer.AI_TRIAGE)
 
         return None
 
@@ -399,3 +456,79 @@ class TriageService:
 
     def _set_cache(self, key: str, data: dict[str, Any]) -> None:
         self._cache_manager.set(key, data, ttl=3600)
+
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
+            try:
+                outcome["response"] = self._llm.call(
+                    prompt=prompt,
+                    max_tokens=self._config.ai_triage_max_tokens,
+                    temperature=0.0,
+                )
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
+        Only used when the LLM call failed; the stale skill must still exist
+        in the current candidate set (a removed skill is never resurrected).
+        """
+        if not stale_entry:
+            return None
+        try:
+            skill_id = str(stale_entry["skill_id"])
+            if not self._skill_in_candidates(skill_id, candidates):
+                return None
+            return SkillRoute(
+                skill_id=skill_id,
+                confidence=float(stale_entry["confidence"]),
+                layer=RoutingLayer.AI_TRIAGE,
+                source=str(stale_entry.get("source", "")),
+                description=str(stale_entry.get("description", "")),
+                metadata={
+                    "ai_triage": True,
+                    "last_good": True,
+                    "candidates_sent": len(candidates),
+                },
+            )
+        except (KeyError, TypeError, ValueError) as e:
+            logger.debug("Failed to build last-good route: %s", e)
+            return None

## diff: scripts
1c1,239
< NEW_FILE
---
> #!/usr/bin/env python3
> """Build an extended routing eval set from production logs (M1c).
(scripts 为未跟踪新文件,全文见下)

## scripts/build_eval_from_logs.py merge 段
148:def merge_confirmed(extended_path: Path, main_path: Path = MAIN_EVAL) -> int:
149-    """Append human-confirmed entries (needs_review: false, expect set)
150-    from the extended file into the main eval set, and drop them from the
151-    extended file. Returns the number of merged entries."""
152-    extended = yaml.safe_load(extended_path.read_text(encoding="utf-8")) or []
153-    main = yaml.safe_load(main_path.read_text(encoding="utf-8")) or []
154-    main_queries = {normalize(e["query"]) for e in main}
155-
156-    confirmed, remaining, skipped = [], [], 0
157-    for e in extended:
158-        if not isinstance(e.get("query"), str):
159-            # Hand-edited entries missing "query" can't be keyed — keep them
160-            # in the extended file instead of crashing mid-merge.
            remaining.append(e)
    if skipped:
        print(
            f"Warning: skipped {skipped} extended entries missing 'query'.",
            file=sys.stderr,
        )

    if confirmed:
        main_text = main_path.read_text(encoding="utf-8")
        # A main file without a trailing newline would glue the last entry
        # onto the first appended line and corrupt the YAML.
        if main_text and not main_text.endswith("\n"):
            main_text += "\n"
        atomic_writer.write_text(
            main_path,
            main_text + yaml.safe_dump(confirmed, allow_unicode=True, sort_keys=False),
        )
        atomic_writer.write_text(
            extended_path,
            yaml.safe_dump(remaining, allow_unicode=True, sort_keys=False),
        )
    return len(confirmed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analytics", type=Path, help="path to analytics.jsonl")
    parser.add_argument("--triage", type=Path, help="path to ai_triage_log.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--n", type=int, default=130, help="sample size")
    parser.add_argument("--seed", type=int, default=42, help="sampling seed")

## scripts/replay_routing.py docstring
#!/usr/bin/env python3
"""Offline replay harness for historical routing decisions (M1b).

Re-routes queries from a project's analytics.jsonl with the current code
and diffs the new decisions against the recorded ones: agreement rate,
old-vs-new layer distribution, and the top changed queries. Use --no-llm
to disable AI triage and replay only the deterministic layers (the config
knob RoutingConfig.enable_ai_triage=False, same as eval_routing.py's
record_telemetry=False escape hatch, keeps replay from writing telemetry).

Warning: without --no-llm, replay makes REAL LLM calls (costs money) and
writes real entries to the project's .vibe/triage_cache.json — the
record_telemetry=False flag only suppresses analytics telemetry, it does
not isolate the persistent triage cache.

Usage:
    uv run python scripts/replay_routing.py \
        --log /path/.vibe/analytics.jsonl [--project-root /path] \
        [--limit 200] [--no-llm] [--output replay-report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

