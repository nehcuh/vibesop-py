# 门禁3 复审(第二轮):M3 收尾三项修复

## 修复项
1. scenario 命中时 triage force=True(unified.py _try_layers Step 2: force=(not use_keyword) or (scenario_candidate is not None)),跳过 short-query bypass 让 triage 真正仲裁;triage 无结果仍回退 scenario。
2. embedding 缓存 entry 加 model 字段,与当前 MODEL_NAME 不一致则重编码(旧缓存无 model 字段自然 stale 一次)。
3. 垃圾过滤 guard 下沉:_junk_query_result() 辅助函数,_single_skill_route 头部加 guard(orchestrator/sessions/plan_builder/workflow_engine 四个调用方路径覆盖),route() 入口 guard 保留(仍在遥测块之前)。

## 开发者声明
orchestrate 路径长垃圾 query 拿到 no-match 后仍可能经 _heuristic_check 进 decompose——所有长 no-match query 的既有行为,未加重未修复。

## diff: unified.py
diff --git a/src/vibesop/core/routing/unified.py b/src/vibesop/core/routing/unified.py
index 08417a5..7349c1c 100644
--- a/src/vibesop/core/routing/unified.py
+++ b/src/vibesop/core/routing/unified.py
@@ -66,6 +66,38 @@ if TYPE_CHECKING:
 
 logger = logging.getLogger(__name__)
 
+# Harness-injected context marker (e.g. Kimi Code / Claude Code system
+# reminders). Production logs showed <system-reminder> blocks reaching
+# route() as if they were user queries, producing garbage matches and
+# polluting miss analytics. Queries containing this marker are rejected
+# at the routing entry point with a no-match result, before any matching
+# layer, telemetry, or analytics write. (Constant, not config: there is
+# no legitimate reason to route harness markup.)
+_SYSTEM_REMINDER_MARKER = "<system-reminder"
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
@@ -408,6 +440,14 @@ class UnifiedRouter(
         context: RoutingContext | None = None,
     ) -> RoutingResult:
         """Internal: route a query to the best matching skill."""
+        # Junk guard (defense in depth): Orchestrator, session context, and
+        # PlanBuilder call this method directly, bypassing route()'s entry
+        # guard, so the same rejection lives here too — before stats,
+        # tracing, and any matching layer. route()'s own guard is kept: it
+        # sits before the telemetry block and additionally skips the
+        # analytics / miss-counter writes.
+        if _SYSTEM_REMINDER_MARKER in query:
+            return _junk_query_result(query)
         start_time = time.perf_counter()
         with self._stats_lock:
             self._total_routes += 1
@@ -543,7 +583,17 @@ class UnifiedRouter(
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
@@ -558,13 +608,18 @@ class UnifiedRouter(
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
@@ -584,6 +639,29 @@ class UnifiedRouter(
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
@@ -624,9 +702,9 @@ class UnifiedRouter(
             self._tracer.record_layer(RoutingLayer.SCENARIO, scen_detail, len(candidates))
 
             idx_match, idx_detail = _layers.try_index_layer(self, query, candidates)  # pyright: ignore[reportArgumentType]
-            routing_path.append(RoutingLayer.AI_TRIAGE)
+            routing_path.append(RoutingLayer.SEMANTIC_INDEX)
             layer_details.append(idx_detail)
-            self._tracer.record_layer(RoutingLayer.AI_TRIAGE, idx_detail, len(candidates))
+            self._tracer.record_layer(RoutingLayer.SEMANTIC_INDEX, idx_detail, len(candidates))
 
             best = max(
                 (m for m in (scen_match, idx_match) if m is not None),
@@ -638,9 +716,9 @@ class UnifiedRouter(
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
 
@@ -830,6 +908,13 @@ class UnifiedRouter(
         Returns:
             RoutingResult with primary match or no-match sentinel.
         """
+        # Junk guard: reject harness-injected <system-reminder> content before
+        # it reaches any matching layer. Returns the same primary=None no-match
+        # shape as fallback_mode="disabled" (minus the matcher-pipeline nearest
+        # scan, which would be meaningless for markup), and skips the telemetry
+        # block below so junk never lands in analytics / the miss counter.
+        if _SYSTEM_REMINDER_MARKER in query:
+            return _junk_query_result(query)
         result = self._single_skill_route(query, candidates, context)
         # P1 telemetry — the single exit point for the single-route path (hit,
         # low-confidence, and no-match/fallback all land here). Both writes are

## diff: triage_recall.py(新文件全文)
"""Embedding-based candidate recall for the AI triage prefilter.

The AI triage prefilter historically ranked candidates with the
KeywordMatcher: a literal-token gate in front of the LLM, so a correct
skill with no lexical overlap never reached the LLM window (and CJK
queries tokenize to single characters, making recall near-random). This
module replaces that gate with semantic recall: candidates are embedded
once (paraphrase-multilingual-MiniLM-L12-v2, same model as the index
embedding fallback in ``_layers.py``), cached on disk, and the query is
ranked against them by cosine similarity.

Persistence follows the ``TriageCache`` pattern
(``.vibe/skill_embeddings.json``): non-blocking advisory cross-process
lock, atomic temp+rename writes, corruption self-heals on the next
write, and fail-open semantics — any failure (missing optional
dependency, model load error, lock contention, IO) returns ``None`` so
the caller falls back to the KeywordMatcher path. Each cache entry also
carries the embedding model name; entries written by a different model
are treated as stale and re-encoded, so switching ``MODEL_NAME`` never
silently reuses incompatible vectors.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_HASH_LENGTH = 16


class EmbeddingRecall:
    """Semantic top-N candidate recall with a persistent embedding cache."""

    def __init__(self, storage_dir: str | Path = ".vibe") -> None:
        self.cache_path = Path(storage_dir) / "skill_embeddings.json"
        self.lock_path = Path(storage_dir) / "skill_embeddings.lock"
        self._model: Any | None = None
        self._model_failed = False

    def recall(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int,
    ) -> list[str] | None:
        """Return up to ``top_n`` candidate ids ranked by embedding similarity.

        ``None`` on any failure — the caller must fall back to keyword
        prefiltering.
        """
        try:
            model = self._get_model()
            if model is None:
                return None
            embeddings = self._candidate_embeddings(model, candidates)
            if not embeddings:
                return None
            query_emb = self._encode(model, [query])[0]
            scored = sorted(
                (
                    (str(c["id"]), _cosine_similarity(query_emb, embeddings[str(c["id"])]))
                    for c in candidates
                    if str(c.get("id", "")) in embeddings
                ),
                key=lambda kv: kv[1],
                reverse=True,
            )
            return [skill_id for skill_id, _ in scored[:top_n]]
        except Exception as e:  # recall must never break routing
            logger.debug("Embedding recall unavailable: %s", e)
            return None

    def _get_model(self) -> Any | None:
        """Lazy-load the model once per instance; failures are sticky."""
        if self._model is not None:
            return self._model
        if self._model_failed:
            return None
        try:
            from sentence_transformers import (
                SentenceTransformer,  # pyright: ignore[reportMissingImports]
            )

            self._model = SentenceTransformer(MODEL_NAME)
        except Exception as e:
            logger.debug("sentence-transformers unavailable for triage recall: %s", e)
            self._model_failed = True
            return None
        return self._model

    def _candidate_embeddings(
        self,
        model: Any,
        candidates: list[dict[str, Any]],
    ) -> dict[str, list[float]]:
        """Return embeddings for all candidates; re-encode only content changes."""
        cached = self._read_cache() or {}
        texts = {str(c["id"]): self._candidate_text(c) for c in candidates if c.get("id")}
        stale = [
            sid
            for sid, text in texts.items()
            if not isinstance(cached.get(sid), dict)
            or cached[sid].get("content_hash") != _content_hash(text)
            # Vectors are model-specific: an entry written by a different
            # embedding model (or by a pre-model-versioning build, which
            # lacks the field) must be re-encoded, never silently reused.
            or cached[sid].get("model") != MODEL_NAME
        ]
        if stale:
            vectors = self._encode(model, [texts[sid] for sid in stale])
            now = time.time()
            for sid, vector in zip(stale, vectors, strict=True):
                cached[sid] = {
                    "content_hash": _content_hash(texts[sid]),
                    "model": MODEL_NAME,
                    "embedding": vector,
                    "ts": now,
                }
            self._write_cache(cached)
        return {
            sid: entry["embedding"]
            for sid, entry in cached.items()
            if sid in texts and isinstance(entry, dict) and isinstance(entry.get("embedding"), list)
        }

    @staticmethod
    def _candidate_text(candidate: dict[str, Any]) -> str:
        parts = [
            str(candidate.get("id", "")),
            str(candidate.get("description", "")),
            str(candidate.get("intent", "")),
        ]
        for key in ("triggers", "keywords", "scenarios"):
            values = candidate.get(key) or []
            if isinstance(values, (list, tuple)):
                parts.extend(str(v) for v in values)
        return " ".join(p for p in parts if p)

    @staticmethod
    def _encode(model: Any, texts: list[str]) -> list[list[float]]:
        raw = model.encode(texts, show_progress_bar=False)
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in raw]

    def _read_cache(self) -> dict[str, Any] | None:
        """Read cache state; corruption/contention returns None (self-heals
        on the next ``_write_cache``)."""
        if not self.cache_path.exists():
            return None
        try:
            from vibesop.utils.file_lock import cross_process_lock

            with (
                cross_process_lock(self.lock_path, blocking=False),
                self.cache_path.open("r", encoding="utf-8") as f,
            ):
                data = json.load(f)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _write_cache(self, data: dict[str, Any]) -> None:
        """Persist cache state; any failure is skipped silently (the next
        route re-encodes and retries)."""
        try:
            from vibesop.utils.file_lock import cross_process_lock

            with cross_process_lock(self.lock_path, blocking=False):
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = self.cache_path.with_suffix(".tmp")
                with tmp_path.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                tmp_path.replace(self.cache_path)
        except Exception as e:
            logger.debug("Embedding cache write skipped: %s", e)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_HASH_LENGTH]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b + 1e-10)
