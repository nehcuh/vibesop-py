# 门禁 6b 复审包:D BLOCK 修复 + 同轮 nits 收敛

## 背景

gate6 双路复审:pi BLOCK + claude BLOCK,根因一致——D 切片(orphan 清理)的 .vibe-manifest.json 标记机制不覆盖 vibe 自有渲染/拷贝主路径(_render_skill_content 内容分支 base.py:475、copy 兜底 :532/:550、pack_installer.py:791),导致 vibe 渲染的 orphan 永不清理,docstring 承诺失效,且旧测试被回改掩盖。A/B/C 通过,留 5 NIT 同轮收敛。

## 本轮修复内容

### D BLOCK 修复(agent-28)
- base.py 新增 SKILL_MARKER_FILE 常量 + write_skill_marker() helper(极简 JSON {id, source:{type,path}},不伪造 checksum;已有标记直接返回,源标记优先)
- _render_skill_content 内容命中分支写 source.type="render" 标记;copy 兜底分支写 "pack-copy"(write 失败仅 warning,不丢产物)
- pack_installer.py:791 _copy_skill_dirs 写 "pack-copy" 标记(lazy import 避免顶层耦合)
- clean_orphan_skills docstring 如实化;新增 skip 计数 + logger.info 汇总(observability nit,renderer.py 未授权改动)
- 测试:旧 fixture 手工补 marker 的回改已还原为走真实渲染路径;新增"渲染产物从 manifest 移除后能被清理"回归测试;copy fallback 写标记/保留源标记;pack_installer 两个新测试
- 备注:_fallback_skill_content stub 分支(无内容来源时)未写标记,移出 manifest 后按 user-owned 保护——保守方向,记录为后续候选 nit

### 同轮 nits
- NIT-A1: decompose 正常 --json 分支 console.print → print()(与 junk 分支和 route --json 基准统一;新增 160 字符长 query 的 json.loads 可解析测试)
- NIT-A2: AgentRouter.decompose() docstring 注明 junk 返回 [] 与合法无分解不可区分
- NIT-B1: docs/user/CLI_REFERENCE.md 环境变量表补 VIBE_AI_TRIAGE_ENABLED 行(只 gate LLM 不 gate 缓存;全量 kill switch 是 enable_ai_triage);CHANGELOG.md Unreleased 记录 B(b) 与 C 的用户可感知变更(投机写 index_match_threshold 的用户从静默忽略变为生效,越界启动报错)
- pi 测试缺口: VIBE_AI_TRIAGE_ENABLED=0 真实 env 路径测试(monkeypatch.setenv,断言 fresh 命中返回且 init_llm_client 未被调用)

## 验证

合并后 1805 passed, 2 skipped, 0 failed(tests/unit/core/routing + tests/core/routing + test_config_manager + adapters + installer + cli + agent)。ruff 全过。

## 请重点攻击的点

1. write_skill_marker 的"源标记优先"是否完备:copytree 连带的中心库标记与渲染标记会不会出现语义冲突?
2. 渲染分支写标记失败仅 warning——会不会重新引入"渲染产物无标记→永不清理"的静默缺口?
3. pack_installer lazy import 的耦合规避是否引入循环风险?
4. 还原后的旧测试是否真实经过渲染路径而非另一种形态的手工 fixture?
5. CLI_REFERENCE 的 env var 文案与实际语义逐字核对。

## src diff(累计,含 gate6 原改动)

diff --git a/src/vibesop/adapters/base.py b/src/vibesop/adapters/base.py
index 6e6d208..9cedd59 100644
--- a/src/vibesop/adapters/base.py
+++ b/src/vibesop/adapters/base.py
@@ -4,6 +4,7 @@ This module provides the abstract base class that all platform
 adapters must inherit from, along with shared utility methods.
 """
 
+import json
 import logging
 from abc import ABC, abstractmethod
 from pathlib import Path
@@ -14,6 +15,48 @@ from vibesop.security import PathSafety, SecurityScanner
 
 logger = logging.getLogger(__name__)
 
+# Marker file identifying a skill directory as vibe-managed.  Written into
+# central storage at install time by ``SkillStorage._write_metadata`` and
+# into rendered/copied platform dirs by ``write_skill_marker``.
+# ``clean_orphan_skills`` only removes dirs carrying this marker.
+SKILL_MARKER_FILE = ".vibe-manifest.json"
+
+
+def write_skill_marker(
+    skill_dir: Path,
+    skill_id: str,
+    source_type: str,
+    source_path: str = "",
+) -> None:
+    """Write a vibe-ownership marker into a rendered/copied skill directory.
+
+    Minimal companion to ``SkillStorage._write_metadata`` (which writes the
+    full SkillManifest into central storage).  Rendered platform dirs lack
+    full source metadata, so only ownership-identifying fields are written
+    and no checksum is fabricated.  Does nothing when a marker already
+    exists (e.g. carried over by copytree from central storage) — the
+    source marker always wins.
+
+    Args:
+        skill_dir: Skill directory receiving the marker
+        skill_id: Skill identifier recorded in the marker
+        source_type: Origin kind, e.g. "render" or "pack-copy"
+        source_path: Optional origin path for copy provenance
+    """
+    marker_path = skill_dir / SKILL_MARKER_FILE
+    if marker_path.exists():
+        return
+    payload = {
+        "id": skill_id,
+        "source": {
+            "type": source_type,
+            "path": source_path,
+            "version": None,
+            "ref": None,
+        },
+    }
+    marker_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
+
 
 class PlatformAdapter(ABC):
     """Abstract base class for platform adapters.
@@ -145,13 +188,22 @@ class PlatformAdapter(ABC):
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
+        ``.vibe-manifest.json`` marker, written either at install time
+        by :meth:`SkillStorage._write_metadata` or at render/copy time
+        by :func:`write_skill_marker`.  Directories without a marker
+        are treated as user/third-party content and are skipped
+        untouched (counted in a summary log).  Orphan symlinks are
+        unlinked as before.
+
+        This prevents stale skills from lingering in platform configs
+        after they have been deleted from the registry, without
+        deleting user-owned skills in shared directories.
 
         Adapters that do not manage skills (``manages_skills = False``)
         skip cleanup entirely to avoid deleting third-party skills in
@@ -176,20 +228,42 @@ class PlatformAdapter(ABC):
         expected_dirs = {skill.id.replace("/", "-") for skill in manifest.skills}
 
         removed: list[Path] = []
+        skipped_user_owned = 0
         for item in skills_dir.iterdir():
             if not item.is_dir() and not item.is_symlink():
                 continue
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
+                elif (item / SKILL_MARKER_FILE).exists():
+                    # Only remove orphans that vibe manages (marker file
+                    # written at install/render/copy time); user-owned
+                    # dirs are kept.
+                    try:
                         shutil.rmtree(item)
-                    removed.append(item)
-                except OSError as e:
-                    logger.debug(f"Failed to remove orphan skill dir {item}: {e}")
+                        removed.append(item)
+                    except OSError as e:
+                        logger.debug(f"Failed to remove orphan skill dir {item}: {e}")
+                else:
+                    skipped_user_owned += 1
+                    logger.debug(
+                        f"Skipping orphan skill dir {item}: no {SKILL_MARKER_FILE}, "
+                        "treating as user-owned content"
+                    )
+
+        if skipped_user_owned:
+            logger.info(
+                "Orphan cleanup: skipped %d user-owned skill dir(s) without %s",
+                skipped_user_owned,
+                SKILL_MARKER_FILE,
+            )
 
         return removed
 
@@ -454,6 +528,12 @@ class PlatformAdapter(ABC):
         if skill_content:
             skill_content = self._normalize_skill_type(skill_content)
             self.write_file_atomic(skill_output_path, skill_content, validate_security=False)
+            # Ownership marker so clean_orphan_skills can reclaim this dir
+            # once the skill leaves the manifest.
+            try:
+                write_skill_marker(skill_dir, skill_id, "render")
+            except OSError as e:
+                logger.warning("skill rendered but marker write failed for %s: %s", skill_dir, e)
             result.add_file(skill_output_path)
             return
 
@@ -531,6 +611,11 @@ class PlatformAdapter(ABC):
                     from vibesop.core.skills.storage import write_copy_source_marker
 
                     write_copy_source_marker(skill_dir, resolved_installed)
+                    # Ownership marker for orphan cleanup; keeps the source
+                    # marker if copytree already carried one over.
+                    write_skill_marker(
+                        skill_dir, skill_id, "pack-copy", str(resolved_installed)
+                    )
                 except OSError as marker_err:
                     logger.warning(
                         "copy succeeded but copy-source marker write failed for %s: %s",
diff --git a/src/vibesop/agent/__init__.py b/src/vibesop/agent/__init__.py
index 0aef454..6da5486 100644
--- a/src/vibesop/agent/__init__.py
+++ b/src/vibesop/agent/__init__.py
@@ -197,8 +197,21 @@ class AgentRouter:
         }
 
     def decompose(self, query: str) -> list[dict[str, str]]:
-        """Decompose a complex query into independent sub-tasks."""
+        """Decompose a complex query into independent sub-tasks.
+
+        Returns an empty list both for junk queries (harness-injected markup,
+        rejected by the ``_is_junk_query`` guard) and for legitimate
+        single-intent queries with nothing to decompose — the two cases are
+        indistinguishable to the caller at this API layer. The ``vibe
+        decompose`` CLI command prints a distinct rejection message for junk.
+        """
         from vibesop.core.orchestration import TaskDecomposer
+        from vibesop.core.routing.unified import _is_junk_query
+
+        # Junk guard: harness-injected markup is not a user query — return an
+        # empty decomposition (same predicate as the route() entry guard).
+        if _is_junk_query(query):
+            return []
 
         # Initialize decomposer with injected LLM
         decomposer = TaskDecomposer(llm_client=self._router.llm)
@@ -228,13 +241,20 @@ class AgentRouter:
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
index 2936976..d523191 100644
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
@@ -1086,7 +1102,10 @@ def decompose(
     if json_output:
         import json
 
-        console.print(
+        # Plain print (not console.print) so rich never wraps the JSON — a
+        # wrapped line inside a string value breaks json.loads. Same output
+        # channel as the junk-guard branch above and route --json (:1055).
+        print(
             json.dumps(
                 {
                     "query": query,
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
diff --git a/src/vibesop/installer/pack_installer.py b/src/vibesop/installer/pack_installer.py
index 75cc6c9..1ab8559 100644
--- a/src/vibesop/installer/pack_installer.py
+++ b/src/vibesop/installer/pack_installer.py
@@ -790,6 +790,18 @@ class PackInstaller:
 
             shutil.copytree(skill_dir, dest_path)
             write_copy_source_marker(dest_path, skill_dir)
+            # Ownership marker so clean_orphan_skills can reclaim this dir;
+            # keeps the source marker if copytree already carried one over.
+            try:
+                from vibesop.adapters.base import write_skill_marker
+
+                write_skill_marker(dest_path, flat_name, "pack-copy", str(skill_dir))
+            except OSError as marker_err:
+                logger.warning(
+                    "copy succeeded but ownership marker write failed for %s: %s",
+                    dest_path,
+                    marker_err,
+                )
             if dedupe_by_name:
                 skill_name = self._parse_skill_name(skill_file)
                 if skill_name and skill_name not in existing_names:

## tests diff(累计)

diff --git a/tests/adapters/test_base.py b/tests/adapters/test_base.py
index 4c1224a..1ccb44a 100644
--- a/tests/adapters/test_base.py
+++ b/tests/adapters/test_base.py
@@ -1,6 +1,7 @@
 """Tests for PlatformAdapter base class."""
 
 from pathlib import Path
+from types import SimpleNamespace
 
 import pytest
 
@@ -305,16 +306,22 @@ class TestPlatformAdapterEdgeCases:
         errors = adapter.validate_manifest(manifest)
         assert errors == []
 
-    def test_clean_orphan_skills(self, tmp_path: Path) -> None:
-        """Test clean_orphan_skills removes unexpected directories."""
+    def test_clean_orphan_skills(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
+        """Test clean_orphan_skills removes vibe-managed orphan directories."""
         adapter = DummyAdapter()
         skills_dir = tmp_path / "skills"
         skills_dir.mkdir()
 
-        # Create an orphan dir
+        # Produce the orphan through the real render path —
+        # _render_skill_content writes .vibe-manifest.json as the
+        # ownership marker (no hand-crafted fixture).
         orphan = skills_dir / "old-skill"
         orphan.mkdir()
-        (orphan / "SKILL.md").write_text("# Old", encoding="utf-8")
+        monkeypatch.setattr(adapter, "_find_skill_content", lambda _: "# Old")
+        adapter._render_skill_content(
+            SimpleNamespace(id="old-skill"), orphan, RenderResult(success=True)
+        )
+        assert (orphan / ".vibe-manifest.json").exists()
 
         # Create a valid skill dir
         valid = skills_dir / "valid-skill"
@@ -332,6 +339,104 @@ class TestPlatformAdapterEdgeCases:
         assert not orphan.exists()
         assert valid.exists()
 
+    def test_rendered_skill_is_cleaned_after_manifest_removal(
+        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """Regression: a skill dir produced by the render content-hit branch
+        (base.py: SKILL.md + marker, no copy) is reclaimed once the skill
+        leaves the manifest."""
+        adapter = DummyAdapter()
+        skills_dir = tmp_path / "skills"
+        skills_dir.mkdir()
+
+        skill_dir = skills_dir / "rendered-skill"
+        skill_dir.mkdir()
+        monkeypatch.setattr(adapter, "_find_skill_content", lambda _: "# Rendered")
+        adapter._render_skill_content(
+            SimpleNamespace(id="rendered-skill"), skill_dir, RenderResult(success=True)
+        )
+        assert (skill_dir / "SKILL.md").exists()
+        assert (skill_dir / ".vibe-manifest.json").exists(), (
+            "render path must write the ownership marker"
+        )
+
+        # Skill removed from registry → empty manifest → orphan cleanup
+        metadata = ManifestMetadata(platform="dummy-platform")
+        manifest = Manifest(metadata=metadata)
+
+        removed = adapter.clean_orphan_skills(manifest, tmp_path)
+
+        assert removed == [skill_dir]
+        assert not skill_dir.exists()
+
+    def test_render_copy_fallback_writes_ownership_marker(
+        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """The copy fallback branch writes .vibe-manifest.json alongside the
+        copy-source marker when the installed source dir has no marker."""
+        adapter = DummyAdapter()
+        skills_dir = tmp_path / "skills"
+        skills_dir.mkdir()
+
+        installed = tmp_path / "installed" / "pack-skill"
+        installed.mkdir(parents=True)
+        (installed / "SKILL.md").write_text("# Pack skill", encoding="utf-8")
+
+        skill_dir = skills_dir / "pack-skill"
+        monkeypatch.setattr(adapter, "_find_skill_content", lambda _: None)
+        monkeypatch.setattr(
+            "vibesop.adapters._shared.is_pack_installed", lambda _: installed
+        )
+        monkeypatch.setattr(
+            "vibesop.utils.symlinks.can_create_dir_symlink", lambda _: False
+        )
+
+        adapter._render_skill_content(
+            SimpleNamespace(id="pack-skill"), skill_dir, RenderResult(success=True)
+        )
+
+        assert (skill_dir / "SKILL.md").exists()
+        marker = skill_dir / ".vibe-manifest.json"
+        assert marker.exists(), "copy fallback must write the ownership marker"
+        import json
+
+        data = json.loads(marker.read_text(encoding="utf-8"))
+        assert data["id"] == "pack-skill"
+        assert data["source"]["type"] == "pack-copy"
+
+    def test_render_copy_fallback_preserves_source_marker(
+        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """If the source dir already carries a marker, copytree keeps it and
+        the fallback must not overwrite it."""
+        adapter = DummyAdapter()
+        skills_dir = tmp_path / "skills"
+        skills_dir.mkdir()
+
+        installed = tmp_path / "installed" / "pack-skill"
+        installed.mkdir(parents=True)
+        (installed / "SKILL.md").write_text("# Pack skill", encoding="utf-8")
+        (installed / ".vibe-manifest.json").write_text(
+            '{"id": "pack-skill", "source": {"type": "local"}}', encoding="utf-8"
+        )
+
+        skill_dir = skills_dir / "pack-skill"
+        monkeypatch.setattr(adapter, "_find_skill_content", lambda _: None)
+        monkeypatch.setattr(
+            "vibesop.adapters._shared.is_pack_installed", lambda _: installed
+        )
+        monkeypatch.setattr(
+            "vibesop.utils.symlinks.can_create_dir_symlink", lambda _: False
+        )
+
+        adapter._render_skill_content(
+            SimpleNamespace(id="pack-skill"), skill_dir, RenderResult(success=True)
+        )
+
+        assert (skill_dir / ".vibe-manifest.json").read_text(encoding="utf-8") == (
+            '{"id": "pack-skill", "source": {"type": "local"}}'
+        ), "source marker must be preserved"
+
     def test_clean_orphan_skills_no_skills_dir(self, tmp_path: Path) -> None:
         """Test clean_orphan_skills when skills dir doesn't exist."""
         adapter = DummyAdapter()
@@ -404,6 +509,9 @@ class TestPlatformAdapterEdgeCases:
         orphan = skills_dir / "old-skill"
         orphan.mkdir()
         (orphan / "SKILL.md").write_text("# Old", encoding="utf-8")
+        # The marker normally comes from the render/install path; written
+        # by hand here to keep this test focused on the manages_skills flag.
+        (orphan / ".vibe-manifest.json").write_text("{}", encoding="utf-8")
 
         valid = skills_dir / "valid-skill"
         valid.mkdir()
@@ -420,6 +528,45 @@ class TestPlatformAdapterEdgeCases:
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
diff --git a/tests/installer/test_pack_installer.py b/tests/installer/test_pack_installer.py
index 96b1766..815abdb 100644
--- a/tests/installer/test_pack_installer.py
+++ b/tests/installer/test_pack_installer.py
@@ -299,6 +299,59 @@ class TestSkillSymlinks:
 
         assert count == 2
 
+    def test_copy_skill_dirs_writes_ownership_marker(self, tmp_path):
+        """Copied skill dirs get .vibe-manifest.json so clean_orphan_skills
+        can reclaim them later."""
+        import json
+
+        from vibesop.installer.pack_installer import PackInstaller
+
+        central = tmp_path / "central"
+        pack = central / "testpack"
+        skill_dir = pack / "review"
+        skill_dir.mkdir(parents=True)
+        (skill_dir / "SKILL.md").write_text(
+            "---\nname: review\ndescription: Review code changes\n---\n# Test skill",
+            encoding="utf-8",
+        )
+
+        platform = tmp_path / "platform"
+        platform.mkdir(parents=True)
+
+        installer = PackInstaller(central_storage=central, platform_paths=[platform])
+        count = installer._copy_skill_dirs(pack, platform, "testpack")
+
+        assert count == 1
+        marker = platform / "testpack-review" / ".vibe-manifest.json"
+        assert marker.exists(), "pack copy must write the ownership marker"
+        data = json.loads(marker.read_text(encoding="utf-8"))
+        assert data["source"]["type"] == "pack-copy"
+
+    def test_copy_skill_dirs_preserves_source_marker(self, tmp_path):
+        """A marker already present in central storage is kept as-is."""
+        central = tmp_path / "central"
+        pack = central / "testpack"
+        skill_dir = pack / "review"
+        skill_dir.mkdir(parents=True)
+        (skill_dir / "SKILL.md").write_text(
+            "---\nname: review\ndescription: Review code changes\n---\n# Test skill",
+            encoding="utf-8",
+        )
+        (skill_dir / ".vibe-manifest.json").write_text(
+            '{"id": "review", "source": {"type": "local"}}', encoding="utf-8"
+        )
+
+        platform = tmp_path / "platform"
+        platform.mkdir(parents=True)
+
+        installer = PackInstaller(central_storage=central, platform_paths=[platform])
+        installer._copy_skill_dirs(pack, platform, "testpack")
+
+        marker = platform / "testpack-review" / ".vibe-manifest.json"
+        assert marker.read_text(encoding="utf-8") == (
+            '{"id": "review", "source": {"type": "local"}}'
+        ), "source marker must be preserved"
+
 
 class TestPostInstallHook:
     """Tests for _run_post_install build script detection and execution."""
diff --git a/tests/unit/core/routing/test_triage_service.py b/tests/unit/core/routing/test_triage_service.py
index 0ffa904..d2fabc1 100644
--- a/tests/unit/core/routing/test_triage_service.py
+++ b/tests/unit/core/routing/test_triage_service.py
@@ -706,3 +706,159 @@ class TestCacheDirResolution:
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
+    def test_fresh_hit_returned_with_env_var_disabled(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """VIBE_AI_TRIAGE_ENABLED=0 gates only the LLM client: a fresh
+        persistent-cache hit is still served, and the LLM path is never
+        touched (init_llm_client is not even called)."""
+        monkeypatch.setenv("VIBE_AI_TRIAGE_ENABLED", "0")
+        service = _make_service()
+        service._triage_cache = MagicMock()
+        service._triage_cache.lookup.return_value = (self._FRESH_ENTRY, None)
+
+        with patch.object(service, "init_llm_client") as init_spy:
+            result = service.try_ai_triage("debug this", self._CANDIDATES)
+
+        init_spy.assert_not_called()
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

## docs/CHANGELOG diff

diff --git a/CHANGELOG.md b/CHANGELOG.md
index 83a47d5..1e45a23 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -9,6 +9,23 @@ and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0
 
 ## [Unreleased]
 
+### Routing nits convergence — triage cache & threshold config (2026-08-18)
+
+- **AI triage serves fresh persistent-cache hits without an LLM**
+  (`core/routing/triage_service.py`): when the triage LLM is unconfigured,
+  a fresh `.vibe/triage_cache.json` hit (same candidates hash, within TTL)
+  is still returned — a zero-cost replay of a previous LLM routing decision.
+  A miss (or a stale-only entry) still short-circuits to `None` as before,
+  with no last-good fallback on this path. The two kill switches now differ
+  in scope: `VIBE_AI_TRIAGE_ENABLED=0` gates only the LLM call (fresh cache
+  hits are still served); the config-level `enable_ai_triage = false`
+  remains the full kill switch.
+- **`index_match_threshold` is now a formal `RoutingConfig` key**
+  (`core/config/manager.py`): a value set under this key was previously
+  silently ignored by `TolerantConfig`; it now takes effect (default
+  `0.20`, `0.0 <= value < 1.0`). An out-of-range value such as `1.0` now
+  raises a `ValidationError` at startup instead of being ignored.
+
 ### Observability closed-loop — span tracing, aggregator, instinct bridge (2026-07-21)
 
 Agent-internal observability with span-based tracing, a metric-driven loop
diff --git a/docs/user/CLI_REFERENCE.md b/docs/user/CLI_REFERENCE.md
index d819a2c..0aa6fce 100644
--- a/docs/user/CLI_REFERENCE.md
+++ b/docs/user/CLI_REFERENCE.md
@@ -1387,6 +1387,7 @@ export ANTHROPIC_API_KEY=sk-ant-...
 | `OLLAMA_MODEL` | `Qwen3.6-35B-A3B-mlx-mxfp8` | Default Ollama model |
 | `ANTHROPIC_API_KEY` | — | Anthropic API key |
 | `OPENAI_API_KEY` | — | OpenAI API key |
+| `VIBE_AI_TRIAGE_ENABLED` | — | `0`/`false`/`no` disables the AI-triage LLM call only — fresh hits from the persistent triage cache (`.vibe/triage_cache.json`) are still served. Set `enable_ai_triage = false` in config for a full kill switch |
 
 ### Provider Detection Priority
 

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

    def test_normal_query_json_output_parseable_for_long_query(
        self, decompose_spy: list[str]
    ) -> None:
        """Pin: --json output must survive json.loads even for long queries.

        Rich's console.print wraps at terminal width and would insert a raw
        newline inside a JSON string value; the decompose command therefore
        emits JSON via plain print() (same channel as route --json).
        """
        long_query = "debug the failing login test " + "with verbose tracing " * 6
        result = runner.invoke(app, ["decompose", long_query, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["query"] == long_query
        assert len(data["sub_tasks"]) == 1

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
