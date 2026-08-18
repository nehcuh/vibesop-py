# 门禁 6 复审包:Nits 全量收敛(M6)

## 任务范围

收敛双路复审(claude+pi)在历史门禁中标记的全部非阻塞 nits,4 路独立 coder 并行开发,文件不相交:

1. **A. decompose 三入口 junk 守卫**:cli/main.py `vibe decompose`、agent/__init__.py `decompose()` 与 `build_plan()` 自动分解分支,复用 unified._is_junk_query,在任何分解/LLM/统计之前短路。CLI 非 JSON 打黄色拒绝文案,--json 输出空 sub_tasks;agent API 返回空分解。附带任务:全仓核查"contains"文案误述——结论零改动(已准确)。
2. **B. triage_service 双 nit**:(a) `_last_good_route` metadata recall_method 显式置 None(budget/circuit/LLM失败三路径汇合点,长驻进程不再带上一次请求的残留值;LLM失败路径本次召回结果已丢弃故 None 语义正确);(b) LLM 未配置时 fresh 缓存命中仍返回(缓存 lookup 移到 LLM 可用性检查之前;miss 或仅 stale 仍短路 None,刻意不给 last-good)。已知权衡:VIBE_AI_TRIAGE_ENABLED=0 只 gate LLM 不 gate 缓存。
3. **C. index_match_threshold 入 RoutingConfig**:default 0.20,ge=0.0,lt=1.0(lt 排除 1.0 因 _layers.py:488 置信度缩放除以 1.0-threshold);_layers.py:465 getattr 兜底改直接访问(调查结论:生产路径恒为 RoutingConfig,MagicMock 测试路径全部显式设值,getattr 兜底本是摆设)。
4. **D. orphan 清理误删修复**:clean_orphan_skills 只删含 .vibe-manifest.json 的 vibe 管理目录,用户/第三方自有目录(如 cmspark-eval-engineering-gate)跳过;symlink 孤儿保持 unlink;manages_skills=False 语义不变。源于今天 cmspark 部署时自定义技能被 rmtree 的真实事故。

## 验证

合并后受影响目录 1619 passed, 2 skipped, 0 failed。各切片独立验证:A 1036+141、B 368、C 384+53、D 196。ruff 全过。

## 请重点攻击的点

1. B(b) 改变了"LLM 未配置"的语义边界:fresh 缓存命中现在会绕过 LLM 可用性检查返回。是否引入了未预见的风险?VIBE_AI_TRIAGE_ENABLED=0 不 gate 缓存是否可接受?
2. A 的 build_plan 守卫只拦自动分解分支,显式传入 sub_tasks 的外部调用方不拦——这个语义边界是否正确?
3. C 直接属性访问是否真有遗漏的 duck-typed config 路径?
4. D 的 .vibe-manifest.json 判定是否有反例(vibe 安装但不写 manifest 的路径)?
5. 测试是否真钉死行为而非实现细节。

## src diff

diff --git a/src/vibesop/adapters/base.py b/src/vibesop/adapters/base.py
index 6e6d208..c5d5bbc 100644
--- a/src/vibesop/adapters/base.py
+++ b/src/vibesop/adapters/base.py
@@ -145,13 +145,20 @@ class PlatformAdapter(ABC):
         manifest: Manifest,
         output_dir: Path,
     ) -> list[Path]:
-        """Remove skill directories not present in the manifest.
+        """Remove vibe-managed skill directories not present in the manifest.
 
         After rendering, any skill directory in ``output_dir/skills/``
         whose name does not correspond to a skill in the manifest is
-        considered an orphan and removed.  This prevents stale skills
-        from lingering in platform configs after they have been
-        deleted from the registry.
+        considered an orphan.  Only vibe-managed orphans are removed —
+        a directory is vibe-managed when it contains a
+        ``.vibe-manifest.json`` metadata file (written at install time
+        by :meth:`SkillStorage._write_metadata`).  Directories without
+        that marker are treated as user/third-party content and are
+        skipped untouched.  Orphan symlinks are unlinked as before.
+
+        This prevents stale skills from lingering in platform configs
+        after they have been deleted from the registry, without
+        deleting user-owned skills in shared directories.
 
         Adapters that do not manage skills (``manages_skills = False``)
         skip cleanup entirely to avoid deleting third-party skills in
@@ -182,14 +189,26 @@ class PlatformAdapter(ABC):
             if item.name.startswith("."):
                 continue
             if item.name not in expected_dirs:
-                try:
-                    if item.is_symlink():
+                if item.is_symlink():
+                    # Orphan symlinks are unlinked (existing behavior).
+                    try:
                         item.unlink(missing_ok=True)
-                    else:
+                        removed.append(item)
+                    except OSError as e:
+                        logger.debug(f"Failed to remove orphan skill symlink {item}: {e}")
+                elif (item / ".vibe-manifest.json").exists():
+                    # Only remove orphans that vibe manages (marker file
+                    # written at install time); user-owned dirs are kept.
+                    try:
                         shutil.rmtree(item)
-                    removed.append(item)
-                except OSError as e:
-                    logger.debug(f"Failed to remove orphan skill dir {item}: {e}")
+                        removed.append(item)
+                    except OSError as e:
+                        logger.debug(f"Failed to remove orphan skill dir {item}: {e}")
+                else:
+                    logger.debug(
+                        f"Skipping orphan skill dir {item}: no .vibe-manifest.json, "
+                        "treating as user-owned content"
+                    )
 
         return removed
 
diff --git a/src/vibesop/agent/__init__.py b/src/vibesop/agent/__init__.py
index 0aef454..068d472 100644
--- a/src/vibesop/agent/__init__.py
+++ b/src/vibesop/agent/__init__.py
@@ -199,6 +199,12 @@ class AgentRouter:
     def decompose(self, query: str) -> list[dict[str, str]]:
         """Decompose a complex query into independent sub-tasks."""
         from vibesop.core.orchestration import TaskDecomposer
+        from vibesop.core.routing.unified import _is_junk_query
+
+        # Junk guard: harness-injected markup is not a user query — return an
+        # empty decomposition (same predicate as the route() entry guard).
+        if _is_junk_query(query):
+            return []
 
         # Initialize decomposer with injected LLM
         decomposer = TaskDecomposer(llm_client=self._router.llm)
@@ -228,13 +234,20 @@ class AgentRouter:
         """Build an execution plan for a complex query."""
         from vibesop.core.models import WorkflowPattern
         from vibesop.core.orchestration import PlanBuilder, SubTask, TaskDecomposer
+        from vibesop.core.routing.unified import _is_junk_query
 
         # Auto-decompose if sub_tasks not provided. Keep SubTask objects directly
         # so the LLM-assigned skill_id (and task_type) are preserved into PlanBuilder.
         if sub_tasks is None:
-            decomposer = TaskDecomposer(llm_client=self._router.llm)
-            skills = self._router.build_decomposition_skills(query=query)
-            sub_task_objects = decomposer.decompose(query, skills=skills)
+            if _is_junk_query(query):
+                # Junk guard: harness-injected markup is not a user query —
+                # plan from an empty decomposition (same predicate as the
+                # route() entry guard).
+                sub_task_objects: list[SubTask] = []
+            else:
+                decomposer = TaskDecomposer(llm_client=self._router.llm)
+                skills = self._router.build_decomposition_skills(query=query)
+                sub_task_objects = decomposer.decompose(query, skills=skills)
         else:
             # External caller provided dicts — read skill_id/task_type if present.
             sub_task_objects = [
diff --git a/src/vibesop/cli/main.py b/src/vibesop/cli/main.py
index 2936976..320fd85 100644
--- a/src/vibesop/cli/main.py
+++ b/src/vibesop/cli/main.py
@@ -1073,6 +1073,22 @@ def decompose(
 
     from vibesop.core.orchestration import TaskDecomposer
     from vibesop.core.routing import UnifiedRouter
+    from vibesop.core.routing.unified import _is_junk_query
+
+    # Junk guard: harness-injected markup is not a user query — reject before
+    # decomposition (same predicate as the route() entry guard in unified.py).
+    if _is_junk_query(query):
+        if json_output:
+            import json
+
+            # Plain print (not console.print) so rich never wraps the JSON —
+            # a wrapped line inside a string value breaks json.loads.
+            print(json.dumps({"query": query, "sub_tasks": []}, indent=2, ensure_ascii=False))
+        else:
+            console.print(
+                "[yellow]Query rejected: harness-injected markup, not a user query.[/yellow]"
+            )
+        return
 
     router = UnifiedRouter(
         project_root=Path.cwd(),
diff --git a/src/vibesop/core/config/manager.py b/src/vibesop/core/config/manager.py
index 3a6b9e1..f53c6cd 100644
--- a/src/vibesop/core/config/manager.py
+++ b/src/vibesop/core/config/manager.py
@@ -197,6 +197,16 @@ class RoutingConfig(TolerantConfig):
         "long queries rely on LLM semantic triage. "
         "Set to 0 to always use LLM, 200 to always use keyword matching.",
     )
+    index_match_threshold: float = Field(
+        default=0.20,
+        ge=0.0,
+        lt=1.0,
+        description="Hit threshold for bigram token-overlap matching in the "
+        "SEMANTIC_INDEX routing layer. Kept at 0.20 because calibration data "
+        "is insufficient to justify a change; lowering it increases false "
+        "hits (see bigram threshold calibration notes). Must be < 1.0: the "
+        "confidence scaling in _layers.py divides by (1.0 - threshold).",
+    )
     session_aware: bool = Field(
         default=True,
         description="Enable session-state-aware routing for multi-turn conversations",
diff --git a/src/vibesop/core/routing/_layers.py b/src/vibesop/core/routing/_layers.py
index afb1667..bcc499d 100644
--- a/src/vibesop/core/routing/_layers.py
+++ b/src/vibesop/core/routing/_layers.py
@@ -462,7 +462,7 @@ def try_index_layer(
             best_score = score
             best_skill_id = skill_id
 
-    threshold = getattr(router._config, "index_match_threshold", 0.20)
+    threshold = router._config.index_match_threshold
     if best_score < threshold or not best_skill_id:
         # Token overlap missed — try semantic embedding fallback when available.
         emb_match, emb_detail = _try_embedding_fallback(
diff --git a/src/vibesop/core/routing/triage_service.py b/src/vibesop/core/routing/triage_service.py
index a90147c..a00c67f 100644
--- a/src/vibesop/core/routing/triage_service.py
+++ b/src/vibesop/core/routing/triage_service.py
@@ -122,15 +122,6 @@ class TriageService:
         if not self._config.enable_ai_triage:
             return None
 
-        if self._llm is None:
-            self._llm = self.init_llm_client()
-
-        if self._llm is None or not self._llm.configured():
-            # LLM unconfigured means the whole triage layer is off — including
-            # the persistent cache below ("layer closed = fully closed"), even
-            # though a fresh hit itself would cost nothing.
-            return None
-
         # Build augmented query with memory context (before the cache lookup
         # so the persisted key matches what would be sent to the LLM).
         augmented_query = query
@@ -151,9 +142,16 @@ class TriageService:
         # Persistent cross-process cache: fresh entries skip the LLM entirely;
         # stale ones (expired TTL / changed candidates) are kept as last-good.
         # A fresh hit costs nothing (no recall, no LLM call), so it runs
-        # before the prefilter and the budget/circuit gates below — those only
-        # guard the LLM call path. The hash covers the FULL candidate set (not
-        # the prefiltered window), which is what makes lookup possible before
+        # before the LLM-availability check, the prefilter, and the
+        # budget/circuit gates below — those only guard the LLM call path.
+        # Serving a fresh hit with no LLM configured is safe: the entry was
+        # itself an LLM routing decision, the candidates hash proves the
+        # decision context is unchanged, and the session-end guard below is
+        # re-validated on every hit. (Note: VIBE_AI_TRIAGE_ENABLED=0 only
+        # gates the LLM client, so fresh hits are still served under it; the
+        # config-level enable_ai_triage switch above remains the full
+        # kill switch.) The hash covers the FULL candidate set (not the
+        # prefiltered window), which is what makes lookup possible before
         # prefiltering; a changed set demotes the entry to stale, and
         # _last_good_route then re-validates the skill still exists.
         stale_entry: dict[str, Any] | None = None
@@ -201,6 +199,17 @@ class TriageService:
                 except (KeyError, TypeError, ValueError) as e:
                     logger.debug("Failed to deserialize persistent triage entry: %s", e)
 
+        # LLM availability gate: checked AFTER the persistent-cache lookup so
+        # a fresh hit is still served when no LLM is configured; a miss (or a
+        # stale-only entry) falls through to here and short-circuits exactly
+        # as before — no last-good fallback, since a deliberately LLM-less
+        # layer should not extend decayed stale results either.
+        if self._llm is None:
+            self._llm = self.init_llm_client()
+
+        if self._llm is None or not self._llm.configured():
+            return None
+
         # Budget enforcement. Cheap check, runs before the (expensive)
         # prefilter below: a closed gate must not pay the recall cost.
         budget = getattr(self._config, "ai_triage_budget_monthly", 5.0)
@@ -611,7 +620,13 @@ class TriageService:
                     # Last-good: nothing was sent to the LLM (the gates
                     # closed or the call failed before a new prompt).
                     "candidates_sent": 0,
-                    "recall_method": self._last_recall_method,
+                    # No recall fed this route: it replays a stale cache
+                    # entry, so reporting self._last_recall_method here would
+                    # leak the previous request's value (or, on the
+                    # LLM-failure path, a recall whose result was discarded)
+                    # in long-lived processes. Fixed None, same convention as
+                    # the fresh-cache path above.
+                    "recall_method": None,
                 },
             )
         except (KeyError, TypeError, ValueError) as e:

## tests diff

diff --git a/tests/adapters/test_base.py b/tests/adapters/test_base.py
index 4c1224a..440f036 100644
--- a/tests/adapters/test_base.py
+++ b/tests/adapters/test_base.py
@@ -306,15 +306,16 @@ class TestPlatformAdapterEdgeCases:
         assert errors == []
 
     def test_clean_orphan_skills(self, tmp_path: Path) -> None:
-        """Test clean_orphan_skills removes unexpected directories."""
+        """Test clean_orphan_skills removes vibe-managed orphan directories."""
         adapter = DummyAdapter()
         skills_dir = tmp_path / "skills"
         skills_dir.mkdir()
 
-        # Create an orphan dir
+        # Create a vibe-managed orphan dir (marker written at install time)
         orphan = skills_dir / "old-skill"
         orphan.mkdir()
         (orphan / "SKILL.md").write_text("# Old", encoding="utf-8")
+        (orphan / ".vibe-manifest.json").write_text("{}", encoding="utf-8")
 
         # Create a valid skill dir
         valid = skills_dir / "valid-skill"
@@ -404,6 +405,7 @@ class TestPlatformAdapterEdgeCases:
         orphan = skills_dir / "old-skill"
         orphan.mkdir()
         (orphan / "SKILL.md").write_text("# Old", encoding="utf-8")
+        (orphan / ".vibe-manifest.json").write_text("{}", encoding="utf-8")
 
         valid = skills_dir / "valid-skill"
         valid.mkdir()
@@ -420,6 +422,45 @@ class TestPlatformAdapterEdgeCases:
         assert not orphan.exists()
         assert valid.exists()
 
+    def test_clean_orphan_skills_keeps_user_owned_dirs(self, tmp_path: Path) -> None:
+        """Orphan dirs without .vibe-manifest.json are user-owned and kept."""
+        adapter = DummyAdapter()
+        skills_dir = tmp_path / "skills"
+        skills_dir.mkdir()
+
+        # Simulate a hand-written user skill (cmspark incident: no marker file)
+        user_skill = skills_dir / "cmspark-eval-engineering-gate"
+        user_skill.mkdir()
+        (user_skill / "SKILL.md").write_text("# User skill", encoding="utf-8")
+
+        metadata = ManifestMetadata(platform="dummy-platform")
+        manifest = Manifest(metadata=metadata)
+
+        removed = adapter.clean_orphan_skills(manifest, tmp_path)
+
+        assert removed == []
+        assert user_skill.exists(), "user-owned skill must not be deleted"
+
+    def test_clean_orphan_skills_keeps_manifest_dirs(self, tmp_path: Path) -> None:
+        """Skill dirs present in the manifest are kept regardless of marker."""
+        adapter = DummyAdapter()
+        skills_dir = tmp_path / "skills"
+        skills_dir.mkdir()
+
+        valid = skills_dir / "valid-skill"
+        valid.mkdir()
+
+        metadata = ManifestMetadata(platform="dummy-platform")
+        manifest = Manifest(
+            metadata=metadata,
+            skills=[SkillSpec(id="valid-skill", name="Valid", description="desc", trigger_when="")],
+        )
+
+        removed = adapter.clean_orphan_skills(manifest, tmp_path)
+
+        assert removed == []
+        assert valid.exists()
+
     def test_normalize_skill_type(self) -> None:
         """Test _normalize_skill_type proxy method."""
         adapter = DummyAdapter()
diff --git a/tests/core/test_config_manager.py b/tests/core/test_config_manager.py
index 8325449..4bfa71c 100644
--- a/tests/core/test_config_manager.py
+++ b/tests/core/test_config_manager.py
@@ -5,6 +5,7 @@ from __future__ import annotations
 from pathlib import Path
 
 import pytest
+from pydantic import ValidationError
 
 from vibesop.core.config.manager import (
     ConfigManager,
@@ -112,6 +113,7 @@ def test_get_routing_config_type_and_defaults(manager_no_files: ConfigManager) -
     assert rc.enable_ai_triage is True
     assert rc.enable_embedding is False
     assert rc.confirmation_mode == "always"
+    assert rc.index_match_threshold == pytest.approx(0.20)
 
 
 # ---------------------------------------------------------------------------
@@ -453,3 +455,53 @@ def test_get_routing_config_tolerates_legacy_preferences(
     rc = manager.get_routing_config()  # must not raise ValidationError
     assert isinstance(rc, RoutingConfig)
     assert rc.min_confidence == pytest.approx(0.3)
+
+
+# ---------------------------------------------------------------------------
+# 11. routing.index_match_threshold (SEMANTIC_INDEX bigram hit threshold)
+# ---------------------------------------------------------------------------
+
+
+def test_index_match_threshold_default() -> None:
+    """Default stays 0.20 — calibration data is insufficient to justify a change."""
+    assert RoutingConfig().index_match_threshold == pytest.approx(0.20)
+
+
+def test_index_match_threshold_from_project_toml(
+    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
+) -> None:
+    """A [routing] index_match_threshold in .vibe/config.toml takes effect."""
+    vibe_dir = tmp_path / ".vibe"
+    vibe_dir.mkdir()
+    (vibe_dir / "config.toml").write_text(
+        "[routing]\nindex_match_threshold = 0.42\n",
+        encoding="utf-8",
+    )
+    real_resolve = ConfigSource._resolve_config_path  # pyright: ignore[reportPrivateUsage]
+
+    def _no_global(base_dir: Path, name: str) -> Path | None:
+        # Keep the real home ~/.vibe config out of this test.
+        if base_dir == Path.home() / ".vibe":
+            return None
+        return real_resolve(base_dir, name)
+
+    monkeypatch.setattr(
+        ConfigSource,
+        "_resolve_config_path",
+        staticmethod(_no_global),  # type: ignore[arg-type]
+    )
+    manager = ConfigManager(project_root=str(tmp_path))
+    rc = manager.get_routing_config()
+    assert rc.index_match_threshold == pytest.approx(0.42)
+
+
+def test_index_match_threshold_out_of_range_rejected() -> None:
+    """Values outside [0.0, 1.0) are rejected by pydantic — TolerantConfig
+    only ignores unknown keys, it does not relax field constraints. 1.0 is
+    excluded because the confidence scaling divides by (1.0 - threshold)."""
+    with pytest.raises(ValidationError):
+        RoutingConfig(index_match_threshold=1.5)
+    with pytest.raises(ValidationError):
+        RoutingConfig(index_match_threshold=-0.1)
+    with pytest.raises(ValidationError):
+        RoutingConfig(index_match_threshold=1.0)
diff --git a/tests/unit/core/routing/test_triage_service.py b/tests/unit/core/routing/test_triage_service.py
index 0ffa904..a22a7dd 100644
--- a/tests/unit/core/routing/test_triage_service.py
+++ b/tests/unit/core/routing/test_triage_service.py
@@ -706,3 +706,140 @@ class TestCacheDirResolution:
         assert service._triage_cache.cache_path == vibe_dir / "triage_cache.json"
         assert service._embedding_recall is not None
         assert service._embedding_recall.cache_path == vibe_dir / "skill_embeddings.json"
+
+
+class TestLastGoodRecallMethod:
+    """Last-good routes must not leak a previous request's recall_method.
+
+    Regression: _last_good_route used to read the instance attribute
+    self._last_recall_method, which in a long-lived process carried the
+    previous request's value into the budget/circuit/LLM-failure paths.
+    """
+
+    _CANDIDATES: ClassVar = [
+        {"id": "debug-skill", "intent": "debug things"},
+        {"id": "deploy-skill", "intent": "deploy things"},
+        {"id": "review-skill", "intent": "review code"},
+    ]
+    _STALE_ENTRY: ClassVar = {
+        "skill_id": "debug-skill",
+        "confidence": 0.9,
+        "source": "builtin/debug-skill",
+        "description": "debug things",
+    }
+
+    def _make_service_with_llm(self) -> TriageService:
+        # max_skills=2 with 3 candidates forces the prefilter down the
+        # keyword-recall path, setting _last_recall_method = "keyword".
+        service = _make_service(ai_triage_max_skills=2)
+        service._llm = MagicMock()
+        service._llm.configured.return_value = True
+        service._llm.call.return_value = MagicMock(
+            content="debug-skill",
+            model="test",
+            tokens_used=10,
+            input_tokens=5,
+            output_tokens=5,
+        )
+        service._triage_cache = MagicMock()
+        service._triage_cache.lookup.return_value = (None, None)
+        return service
+
+    def _run_successful_triage(self, service: TriageService) -> None:
+        """First request: full prefilter + LLM path, recall_method recorded."""
+        with patch.object(
+            service,
+            "parse_ai_triage_response",
+            return_value={"skill_id": "debug-skill", "structured": True},
+        ):
+            result = service.try_ai_triage("debug", self._CANDIDATES)
+        assert result is not None
+        assert result.match.metadata["recall_method"] == "keyword"
+
+    def test_budget_rejected_last_good_has_no_residual_recall_method(self) -> None:
+        """Second request rejected by the budget gate must not carry the
+        first request's recall_method into its last-good metadata."""
+        service = self._make_service_with_llm()
+        self._run_successful_triage(service)
+
+        service._cost_tracker.get_monthly_cost.return_value = 5.5
+        service._triage_cache.lookup.return_value = (None, self._STALE_ENTRY)
+
+        result = service.try_ai_triage("debug", self._CANDIDATES)
+
+        assert result is not None
+        assert result.match.metadata["last_good"] is True
+        assert result.match.metadata["recall_method"] is None
+
+    def test_circuit_open_last_good_has_no_residual_recall_method(self) -> None:
+        """Second request rejected by an open circuit must not carry the
+        first request's recall_method either."""
+        service = self._make_service_with_llm()
+        self._run_successful_triage(service)
+
+        service._circuit_breaker.trip("manual")
+        service._triage_cache.lookup.return_value = (None, self._STALE_ENTRY)
+
+        result = service.try_ai_triage("debug", self._CANDIDATES)
+
+        assert result is not None
+        assert result.match.metadata["last_good"] is True
+        assert result.match.metadata["recall_method"] is None
+
+    def test_llm_failure_last_good_has_no_recall_method(self) -> None:
+        """On the LLM-failure path the prefilter DID run for this request,
+        but the last-good route replays a stale entry and used none of that
+        recall — recall_method must still be None."""
+        service = self._make_service_with_llm()
+        self._run_successful_triage(service)
+
+        service._llm.call.side_effect = RuntimeError("LLM error")
+        service._triage_cache.lookup.return_value = (None, self._STALE_ENTRY)
+
+        result = service.try_ai_triage("debug", self._CANDIDATES)
+
+        assert result is not None
+        assert result.match.metadata["last_good"] is True
+        assert result.match.metadata["recall_method"] is None
+
+
+class TestLlmUnconfiguredCacheLookup:
+    """With no LLM configured, a fresh persistent-cache hit is still served;
+    a miss short-circuits exactly as before (no last-good fallback)."""
+
+    _FRESH_ENTRY: ClassVar = {
+        "skill_id": "debug-skill",
+        "confidence": 0.9,
+        "source": "builtin/debug-skill",
+        "description": "debug things",
+    }
+    _CANDIDATES: ClassVar = [{"id": "debug-skill", "intent": "debug things"}]
+
+    def _make_unconfigured_service(self) -> TriageService:
+        service = _make_service()
+        service._llm = MagicMock()
+        service._llm.configured.return_value = False
+        service._triage_cache = MagicMock()
+        return service
+
+    def test_fresh_hit_returned_without_llm(self) -> None:
+        service = self._make_unconfigured_service()
+        service._triage_cache.lookup.return_value = (self._FRESH_ENTRY, None)
+
+        result = service.try_ai_triage("debug this", self._CANDIDATES)
+
+        service._llm.call.assert_not_called()
+        assert result is not None
+        assert result.match.skill_id == "debug-skill"
+        assert result.match.metadata["persistent_cache"] is True
+
+    def test_miss_short_circuits_without_llm(self) -> None:
+        """No fresh entry → the layer stays closed; even a stale entry is
+        NOT served as last-good when the LLM was never configured."""
+        service = self._make_unconfigured_service()
+        service._triage_cache.lookup.return_value = (None, self._FRESH_ENTRY)
+
+        result = service.try_ai_triage("debug this", self._CANDIDATES)
+
+        service._llm.call.assert_not_called()
+        assert result is None

## 新增测试文件 tests/unit/core/routing/test_junk_guard_entrypoints.py

"""Junk-query guard coverage for the decompose entry points.

The junk guard (_is_junk_query in vibesop.core.routing.unified) rejects
harness-injected markup (e.g. <system-reminder> blocks) by PREFIX after
lstrip. route() and _single_skill_route() were already guarded; these tests
pin the same semantics at the three decompose entry points:

- ``vibe decompose`` CLI command (vibesop.cli.main.decompose)
- ``AgentRouter.decompose()`` (vibesop.agent)
- ``AgentRouter.build_plan()`` auto-decompose branch (vibesop.agent)
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from vibesop.agent import AgentRouter
from vibesop.cli.main import app
from vibesop.core.orchestration import SubTask, TaskDecomposer

runner = CliRunner()

JUNK_QUERY = "  <system-reminder>Auto permission mode is active</system-reminder>"
# Marker present but NOT at the prefix — a legitimate query discussing the
# marker must not be killed (prefix, not substring, semantics).
DISCUSSION_QUERY = "explain what <system-reminder> blocks do in this repo"
NORMAL_QUERY = "debug the failing login test"


@pytest.fixture()
def decompose_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record TaskDecomposer.decompose calls; return one canned sub-task."""
    calls: list[str] = []

    def fake_decompose(self: TaskDecomposer, query: str, skills: object = None) -> list[SubTask]:
        calls.append(query)
        return [SubTask(intent="debug", query=query, skill_id=None)]

    monkeypatch.setattr(TaskDecomposer, "decompose", fake_decompose)
    return calls


class TestCliDecomposeJunkGuard:
    def test_junk_query_rejected(self, decompose_spy: list[str]) -> None:
        result = runner.invoke(app, ["decompose", JUNK_QUERY])
        assert result.exit_code == 0
        assert "harness-injected markup" in result.output
        # No decomposition happened at all.
        assert decompose_spy == []

    def test_junk_query_json_output(self, decompose_spy: list[str]) -> None:
        result = runner.invoke(app, ["decompose", JUNK_QUERY, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["sub_tasks"] == []
        assert decompose_spy == []

    def test_normal_query_not_rejected(self, decompose_spy: list[str]) -> None:
        result = runner.invoke(app, ["decompose", NORMAL_QUERY, "--json"])
        assert result.exit_code == 0
        assert "harness-injected markup" not in result.output
        data = json.loads(result.output)
        assert len(data["sub_tasks"]) == 1
        assert decompose_spy == [NORMAL_QUERY]

    def test_marker_discussion_query_not_rejected(self, decompose_spy: list[str]) -> None:
        result = runner.invoke(app, ["decompose", DISCUSSION_QUERY, "--json"])
        assert result.exit_code == 0
        assert "harness-injected markup" not in result.output
        assert decompose_spy == [DISCUSSION_QUERY]


class TestAgentDecomposeJunkGuard:
    def test_junk_query_returns_empty(self, tmp_path, decompose_spy: list[str]) -> None:
        agent = AgentRouter(project_root=tmp_path)
        assert agent.decompose(JUNK_QUERY) == []
        assert decompose_spy == []

    def test_normal_query_decomposes(self, tmp_path, decompose_spy: list[str]) -> None:
        agent = AgentRouter(project_root=tmp_path)
        sub_tasks = agent.decompose(NORMAL_QUERY)
        assert len(sub_tasks) == 1
        assert sub_tasks[0]["intent"] == "debug"
        assert decompose_spy == [NORMAL_QUERY]

    def test_marker_discussion_query_not_killed(self, tmp_path, decompose_spy: list[str]) -> None:
        agent = AgentRouter(project_root=tmp_path)
        sub_tasks = agent.decompose(DISCUSSION_QUERY)
        assert len(sub_tasks) == 1
        assert decompose_spy == [DISCUSSION_QUERY]


class TestAgentBuildPlanJunkGuard:
    def test_junk_query_plans_from_empty_decomposition(
        self, tmp_path, decompose_spy: list[str]
    ) -> None:
        agent = AgentRouter(project_root=tmp_path)
        plan = agent.build_plan(JUNK_QUERY)
        assert plan["steps"] == []
        assert decompose_spy == []

    def test_normal_query_auto_decomposes(self, tmp_path, decompose_spy: list[str]) -> None:
        agent = AgentRouter(project_root=tmp_path)
        agent.build_plan(NORMAL_QUERY)
        assert decompose_spy == [NORMAL_QUERY]
